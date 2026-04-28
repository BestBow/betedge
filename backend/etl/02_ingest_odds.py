import os
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

# DB connection
connection_url = URL.create(
    drivername = "postgresql+psycopg2",
    username   = os.getenv('DB_USER'),
    password   = os.getenv('DB_PASSWORD'),
    host       = os.getenv('DB_HOST'),
    port       = int(os.getenv('DB_PORT', 5432)),
    database   = os.getenv('DB_NAME'),
)
engine = create_engine(connection_url)

API_KEY  = os.getenv('ODDS_API_KEY')
BASE_URL = 'https://api.the-odds-api.com/v4'

# Sports to track
# Chosen for data quality + relevance + free tier availability
SPORTS = [
    {'key': 'soccer_epl',                  'title': 'EPL',              'category': 'soccer'},
    {'key': 'soccer_spain_la_liga',         'title': 'La Liga',          'category': 'soccer'},
    {'key': 'soccer_italy_serie_a',         'title': 'Serie A',          'category': 'soccer'},
    {'key': 'soccer_germany_bundesliga',    'title': 'Bundesliga',       'category': 'soccer'},
    {'key': 'soccer_uefa_champs_league',    'title': 'Champions League', 'category': 'soccer'},
    {'key': 'basketball_nba',               'title': 'NBA',              'category': 'basketball'},
    {'key': 'baseball_mlb',                 'title': 'MLB',              'category': 'baseball'},
    {'key': 'icehockey_nhl',                'title': 'NHL',              'category': 'hockey'},
    {'key': 'mma_mixed_martial_arts',       'title': 'MMA',              'category': 'mma'},
]

def fetch_odds(sport_key, region='uk'):
    """Fetch current odds for a sport from OddsAPI."""
    try:
        params = {
            'apiKey':     API_KEY,
            'regions':    region if 'soccer' in sport_key else 'us',
            'markets':    'h2h',
            'oddsFormat': 'decimal',
        }
        resp = requests.get(
            f"{BASE_URL}/sports/{sport_key}/odds",
            params=params, timeout=10
        )
        remaining = resp.headers.get('x-requests-remaining', 'N/A')
        resp.raise_for_status()
        data = resp.json()
        print(f"  {sport_key:<45} {len(data):>3} matches | {remaining} requests left")
        return data
    except requests.RequestException as e:
        print(f"  {sport_key:<45} ERROR: {e}")
        return []

def upsert_match(conn, api_id, sport_key, home_team, away_team, commence_time):
    """Insert match if not exists, return match id."""
    result = conn.execute(text(
        "SELECT id FROM matches WHERE api_id = :api_id"
    ), {'api_id': api_id}).fetchone()

    if result:
        return result[0]

    result = conn.execute(text("""
        INSERT INTO matches (api_id, sport_key, home_team, away_team, commence_time)
        VALUES (:api_id, :sport_key, :home_team, :away_team, :commence_time)
        RETURNING id
    """), {
        'api_id':        api_id,
        'sport_key':     sport_key,
        'home_team':     home_team,
        'away_team':     away_team,
        'commence_time': commence_time,
    })
    return result.fetchone()[0]

def store_odds(conn, match_id, bookmaker, home_odds, away_odds, draw_odds=None):
    """Store an odds snapshot."""
    conn.execute(text("""
        INSERT INTO odds_snapshots
            (match_id, bookmaker, home_odds, away_odds, draw_odds)
        VALUES
            (:match_id, :bookmaker, :home_odds, :away_odds, :draw_odds)
    """), {
        'match_id':  match_id,
        'bookmaker': bookmaker,
        'home_odds': home_odds,
        'away_odds': away_odds,
        'draw_odds': draw_odds,
    })

def get_best_odds(bookmakers, home_team, away_team):
    """Get the best available odds across all bookmakers."""
    best_home = 0
    best_away = 0
    best_draw = 0
    best_home_bm = ''
    best_away_bm = ''

    for bm in bookmakers:
        for market in bm.get('markets', []):
            if market['key'] != 'h2h':
                continue
            for outcome in market['outcomes']:
                name  = outcome['name']
                price = outcome['price']
                if name == home_team and price > best_home:
                    best_home = price
                    best_home_bm = bm['title']
                elif name == away_team and price > best_away:
                    best_away = price
                    best_away_bm = bm['title']
                elif name == 'Draw' and price > best_draw:
                    best_draw = price

    return best_home, best_away, best_draw, best_home_bm, best_away_bm

def compute_implied_prob(odds):
    """Convert decimal odds to implied probability."""
    if not odds or odds <= 1:
        return None
    return round(1 / odds, 4)

def run():
    print(f"\n{'='*55}")
    print(f"  BetEdge ETL — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*55}\n")

    total_matches  = 0
    total_odds     = 0

    with engine.begin() as conn:
        # Upsert sports
        for sport in SPORTS:
            conn.execute(text("""
                INSERT INTO sports (key, title, category)
                VALUES (:key, :title, :category)
                ON CONFLICT (key) DO NOTHING
            """), sport)

        # Fetch and store odds
        print("Fetching odds...\n")
        for sport in SPORTS:
            matches = fetch_odds(sport['key'])
            for match in matches:
                api_id       = match['id']
                home_team    = match['home_team']
                away_team    = match['away_team']
                commence     = match['commence_time']
                bookmakers   = match.get('bookmakers', [])

                if not bookmakers:
                    continue

                # Upsert match
                match_id = upsert_match(
                    conn, api_id, sport['key'],
                    home_team, away_team, commence
                )

                # Store odds snapshot from every bookmaker
                for bm in bookmakers:
                    for market in bm.get('markets', []):
                        if market['key'] != 'h2h':
                            continue
                        outcomes = {o['name']: o['price']
                                    for o in market['outcomes']}
                        home_odds = outcomes.get(home_team)
                        away_odds = outcomes.get(away_team)
                        draw_odds = outcomes.get('Draw')

                        if home_odds and away_odds:
                            store_odds(
                                conn, match_id, bm['title'],
                                home_odds, away_odds, draw_odds
                            )
                            total_odds += 1

                total_matches += 1

    # Verifying the data
    print(f"\n{'─'*55}")
    print(f"Matches stored:      {total_matches}")
    print(f"Odds snapshots:      {total_odds}")

    with engine.connect() as conn:
        for table in ['matches', 'odds_snapshots', 'sports']:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            print(f"  {table:<25} {count:>6} rows")

    print(f"\nETL complete — {datetime.now():%H:%M:%S}")

if __name__ == '__main__':
    run()