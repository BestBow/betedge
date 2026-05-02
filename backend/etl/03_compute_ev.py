import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from difflib import get_close_matches
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

connection_url = URL.create(
    drivername = "postgresql+psycopg2",
    username   = os.getenv('DB_USER'),
    password   = os.getenv('DB_PASSWORD'),
    host       = os.getenv('DB_HOST'),
    port       = int(os.getenv('DB_PORT', 5432)),
    database   = os.getenv('DB_NAME'),
)
engine = create_engine(connection_url)

# ── Load models ───────────────────────────────────────────────
print("Loading models...")
with open('backend/model/club_model.pkl', 'rb') as f:
    club_bundle = pickle.load(f)

with open('backend/model/soccer_model.pkl', 'rb') as f:
    soccer_bundle = pickle.load(f)

club_model    = club_bundle['model']
club_le       = club_bundle['label_encoder']
CLUB_FEATURES = club_bundle['feature_cols']
known_teams   = club_bundle['team_names']

soccer_model    = soccer_bundle['model']
soccer_le       = soccer_bundle['label_encoder']
SOCCER_FEATURES = soccer_bundle['feature_cols']

# ── Load team mapper ──────────────────────────────────────────
with open('backend/model/team_mapper.json') as f:
    MANUAL_MAPPINGS = json.load(f)

# ── Load historical data ──────────────────────────────────────
print("Loading historical data...")
import sqlite3
conn    = sqlite3.connect('data/raw/database.sqlite')
club_df = pd.read_sql("""
    SELECT m.date,
           ht.team_long_name as home_team,
           at.team_long_name as away_team,
           m.home_team_api_id, m.away_team_api_id,
           m.home_team_goal, m.away_team_goal,
           m.B365H, m.B365D, m.B365A
    FROM Match m
    JOIN Team ht ON m.home_team_api_id = ht.team_api_id
    JOIN Team at ON m.away_team_api_id = at.team_api_id
    WHERE m.home_team_goal IS NOT NULL
""", conn)

team_attrs = pd.read_sql("""
    SELECT team_api_id, date, buildUpPlaySpeed,
           defencePressure, defenceAggression,
           chanceCreationShooting
    FROM Team_Attributes
    WHERE buildUpPlaySpeed IS NOT NULL
""", conn)
conn.close()

club_df['date']    = pd.to_datetime(club_df['date'])
team_attrs['date'] = pd.to_datetime(team_attrs['date'])

# International data for soccer model
raw = pd.read_csv('data/raw/results.csv')
raw['date'] = pd.to_datetime(raw['date'])

r1 = pd.read_csv('data/raw/fifa_ranking-2023-07-20.csv')
r2 = pd.read_csv('data/raw/fifa_ranking-2024-04-04.csv')
r3 = pd.read_csv('data/raw/fifa_ranking-2024-06-20.csv')
rankings = pd.concat([r1, r2, r3], ignore_index=True)
rankings = rankings.drop_duplicates(subset=['country_full', 'rank_date'])
rankings['rank_date'] = pd.to_datetime(rankings['rank_date'])
rankings['rank']      = pd.to_numeric(rankings['rank'], errors='coerce')
rankings              = rankings.dropna(subset=['rank'])
rankings              = rankings.rename(columns={'country_full': 'team'})

CLUB_SPORTS = [
    'soccer_epl', 'soccer_spain_la_liga', 'soccer_italy_serie_a',
    'soccer_germany_bundesliga', 'soccer_uefa_champs_league',
    'soccer_france_ligue_one', 'soccer_usa_mls',
]

INTL_SPORTS = [
    'soccer_fifa_world_cup', 'soccer_uefa_euro',
    'soccer_conmebol_copa_libertadores',
]

# ── Team mapper ───────────────────────────────────────────────
def map_team(odds_name):
    if odds_name in MANUAL_MAPPINGS:
        mapped = MANUAL_MAPPINGS[odds_name]
        if mapped in known_teams:
            return mapped
    matches = get_close_matches(odds_name, known_teams, n=1, cutoff=0.6)
    return matches[0] if matches else None

# ── Club feature helpers ──────────────────────────────────────
def get_team_id(team_name):
    rows = club_df[club_df['home_team'] == team_name]['home_team_api_id']
    if rows.empty:
        rows = club_df[club_df['away_team'] == team_name]['away_team_api_id']
    return int(rows.iloc[0]) if not rows.empty else None

def get_club_form(team_name, n=6):
    tid  = get_team_id(team_name)
    if not tid:
        return 0.4, 1.0
    home = club_df[club_df['home_team_api_id'] == tid].copy()
    away = club_df[club_df['away_team_api_id'] == tid].copy()
    home['won'] = (home['home_team_goal'] > home['away_team_goal']).astype(int)
    away['won'] = (away['away_team_goal'] > away['home_team_goal']).astype(int)
    home['pts'] = home.apply(lambda r: 3 if r['home_team_goal'] > r['away_team_goal']
                             else (1 if r['home_team_goal'] == r['away_team_goal'] else 0), axis=1)
    away['pts'] = away.apply(lambda r: 3 if r['away_team_goal'] > r['home_team_goal']
                             else (1 if r['away_team_goal'] == r['home_team_goal'] else 0), axis=1)
    games = pd.concat([
        home[['date','won','pts']],
        away[['date','won','pts']]
    ]).sort_values('date').tail(n)
    if len(games) == 0:
        return 0.4, 1.0
    return float(games['won'].mean()), float(games['pts'].mean())

def get_club_goals(team_name, n=6):
    tid = get_team_id(team_name)
    if not tid:
        return 1.3, 1.2
    home = club_df[club_df['home_team_api_id'] == tid][
        ['date','home_team_goal','away_team_goal']
    ].rename(columns={'home_team_goal':'scored','away_team_goal':'conceded'})
    away = club_df[club_df['away_team_api_id'] == tid][
        ['date','away_team_goal','home_team_goal']
    ].rename(columns={'away_team_goal':'scored','home_team_goal':'conceded'})
    games = pd.concat([home, away]).sort_values('date').tail(n)
    if len(games) == 0:
        return 1.3, 1.2
    return float(games['scored'].mean()), float(games['conceded'].mean())

def get_club_h2h(home_name, away_name):
    hid = get_team_id(home_name)
    aid = get_team_id(away_name)
    if not hid or not aid:
        return 0.45
    h2h = club_df[
        ((club_df['home_team_api_id'] == hid) & (club_df['away_team_api_id'] == aid)) |
        ((club_df['home_team_api_id'] == aid) & (club_df['away_team_api_id'] == hid))
    ].tail(6)
    if len(h2h) == 0:
        return 0.45
    wins = len(h2h[
        ((h2h['home_team_api_id'] == hid) & (h2h['home_team_goal'] > h2h['away_team_goal'])) |
        ((h2h['away_team_api_id'] == hid) & (h2h['away_team_goal'] > h2h['home_team_goal']))
    ])
    return wins / len(h2h)

def get_team_attr(team_name, col):
    tid = get_team_id(team_name)
    if not tid:
        return 50.0
    rows = team_attrs[team_attrs['team_api_id'] == tid]
    if rows.empty:
        return 50.0
    return float(rows.sort_values('date').iloc[-1][col])

def remove_vig(h, d, a):
    ih, id_, ia = 1/h, 1/d, 1/a
    total = ih + id_ + ia
    return ih/total, id_/total, ia/total

def build_club_features(home_name, away_name, home_odds, draw_odds, away_odds):
    hform, hpts    = get_club_form(home_name)
    aform, apts    = get_club_form(away_name)
    hscored, hconc = get_club_goals(home_name)
    ascored, aconc = get_club_goals(away_name)
    h2h            = get_club_h2h(home_name, away_name)
    h_speed        = get_team_attr(home_name, 'buildUpPlaySpeed')
    a_speed        = get_team_attr(away_name, 'buildUpPlaySpeed')
    h_press        = get_team_attr(home_name, 'defencePressure')
    a_press        = get_team_attr(away_name, 'defencePressure')
    mh, md, ma     = remove_vig(home_odds, draw_odds, away_odds)

    return pd.DataFrame([[
        hform, aform, hform-aform,
        hpts, apts,
        hscored, hconc,
        ascored, aconc,
        h2h,
        h_speed, a_speed,
        h_press, a_press,
        mh, md, ma,
    ]], columns=CLUB_FEATURES)

# ── International feature helpers ────────────────────────────
def get_intl_rank(team):
    rows = rankings[rankings['team'] == team]
    if rows.empty:
        return 100.0
    return float(rows.sort_values('rank_date').iloc[-1]['rank'])

def get_intl_form(team, n=10):
    home = raw[raw['home_team'] == team].copy()
    away = raw[raw['away_team'] == team].copy()
    home['won'] = (home['home_score'] > home['away_score']).astype(int)
    away['won'] = (away['away_score'] > away['home_score']).astype(int)
    games = pd.concat([home[['date','won']], away[['date','won']]]).sort_values('date').tail(n)
    return float(games['won'].mean()) if len(games) > 0 else 0.5

def get_intl_goals(team, n=10):
    home = raw[raw['home_team'] == team][['date','home_score','away_score']]\
           .rename(columns={'home_score':'scored','away_score':'conceded'})
    away = raw[raw['away_team'] == team][['date','away_score','home_score']]\
           .rename(columns={'away_score':'scored','home_score':'conceded'})
    games = pd.concat([home, away]).sort_values('date').tail(n)
    if len(games) == 0:
        return 1.5, 1.0
    return float(games['scored'].mean()), float(games['conceded'].mean())

def get_intl_h2h(home, away):
    h2h = raw[
        ((raw['home_team'] == home) & (raw['away_team'] == away)) |
        ((raw['home_team'] == away) & (raw['away_team'] == home))
    ].tail(10)
    if len(h2h) == 0:
        return 0.5
    wins = len(h2h[
        ((h2h['home_team'] == home) & (h2h['home_score'] > h2h['away_score'])) |
        ((h2h['away_team'] == home) & (h2h['away_score'] > h2h['home_score']))
    ])
    return wins / len(h2h)

# ── EV computation ────────────────────────────────────────────
def compute_ev(model_prob, decimal_odds):
    return round((model_prob * (decimal_odds - 1)) - (1 - model_prob), 4)

def compute_edge(model_prob, implied_prob):
    return round(model_prob - implied_prob, 4)

# ── Main run ──────────────────────────────────────────────────
def run():
    print(f"\n{'='*60}")
    print(f"  BetEdge EV Calculator — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*60}\n")

    EV_THRESHOLD   = 0.02
    EDGE_THRESHOLD = 0.03

    flagged   = 0
    processed = 0
    skipped   = 0
    no_map    = 0

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ev_bets"))

        matches = conn.execute(text("""
            SELECT DISTINCT m.id, m.sport_key,
                            m.home_team, m.away_team,
                            m.commence_time
            FROM matches m
            JOIN odds_snapshots o ON m.id = o.match_id
            WHERE m.commence_time > NOW()
              AND m.completed = FALSE
            ORDER BY m.commence_time
        """)).fetchall()

        print(f"Processing {len(matches)} upcoming matches...\n")

        for match in matches:
            match_id  = match[0]
            sport_key = match[1]
            home_team = match[2]
            away_team = match[3]

            # Get best odds
            rows = conn.execute(text("""
                SELECT bookmaker, home_odds, away_odds, draw_odds
                FROM odds_snapshots
                WHERE match_id = :mid
                ORDER BY fetched_at DESC LIMIT 50
            """), {'mid': match_id}).fetchall()

            if not rows:
                skipped += 1
                continue

            best_home = max(float(r[1]) for r in rows)
            best_away = max(float(r[2]) for r in rows)
            draw_list = [float(r[3]) for r in rows if r[3]]
            best_draw = max(draw_list) if draw_list else None
            best_home_bm = next(r[0] for r in rows if float(r[1]) == best_home)
            best_away_bm = next(r[0] for r in rows if float(r[2]) == best_away)

            implied_home = round(1/best_home, 4)
            implied_away = round(1/best_away, 4)
            implied_draw = round(1/best_draw, 4) if best_draw else None

            # ── Get model probabilities ───────────────────────
            model_home = model_away = model_draw = None

            if sport_key in CLUB_SPORTS and best_draw:
                # Map team names
                h_mapped = map_team(home_team)
                a_mapped = map_team(away_team)

                if h_mapped and a_mapped:
                    try:
                        features = build_club_features(
                            h_mapped, a_mapped,
                            best_home, best_draw, best_away
                        )
                        probs      = club_model.predict_proba(features)[0]
                        classes    = club_le.classes_
                        prob_map   = {c: float(p) for c, p in zip(classes, probs)}
                        model_home = prob_map.get('home_win', 0)
                        model_away = prob_map.get('away_win', 0)
                        model_draw = prob_map.get('draw', 0)
                    except Exception as e:
                        skipped += 1
                        continue
                else:
                    no_map += 1
                    # Fall back to devigged market
                    model_home, model_draw, model_away = remove_vig(
                        best_home, best_draw, best_away
                    )

            elif sport_key in INTL_SPORTS:
                hr = get_intl_rank(home_team)
                ar = get_intl_rank(away_team)
                hf = get_intl_form(home_team)
                af = get_intl_form(away_team)
                hs, hc = get_intl_goals(home_team)
                as_, ac = get_intl_goals(away_team)
                h2h = get_intl_h2h(home_team, away_team)

                features = pd.DataFrame([[
                    ar-hr, hr, ar, hf, af, hf-af,
                    h2h, hs, hc, as_, ac, 1, 1.0
                ]], columns=SOCCER_FEATURES)

                probs      = soccer_model.predict_proba(features)[0]
                classes    = soccer_le.classes_
                prob_map   = {c: float(p) for c, p in zip(classes, probs)}
                model_home = prob_map.get('home_win', 0)
                model_away = prob_map.get('away_win', 0)
                model_draw = prob_map.get('draw')

            else:
                # Non-soccer — use devigged market as model
                if best_draw:
                    model_home, model_draw, model_away = remove_vig(
                        best_home, best_draw, best_away
                    )
                else:
                    ih = 1/best_home
                    ia = 1/best_away
                    total = ih + ia
                    model_home = ih/total
                    model_away = ia/total

            if model_home is None:
                skipped += 1
                continue

            # ── Compute EV ────────────────────────────────────
            bets = [
                ('home_win', model_home, implied_home, best_home, best_home_bm),
                ('away_win', model_away, implied_away, best_away, best_away_bm),
            ]
            if best_draw and model_draw:
                bets.append(('draw', model_draw, implied_draw, best_draw, 'best'))

            for bet_on, m_prob, i_prob, odds, bm in bets:
                ev   = compute_ev(m_prob, odds)
                edge = compute_edge(m_prob, i_prob)

                conn.execute(text("""
                    INSERT INTO ev_bets
                        (match_id, bookmaker, bet_on, model_prob,
                         implied_prob, best_odds, expected_value, edge)
                    VALUES
                        (:mid, :bm, :bet_on, :mp,
                         :ip, :odds, :ev, :edge)
                """), {
                    'mid': match_id, 'bm': bm,
                    'bet_on': bet_on,
                    'mp': round(m_prob, 4),
                    'ip': i_prob, 'odds': odds,
                    'ev': ev, 'edge': edge,
                })

                if ev > EV_THRESHOLD and edge > EDGE_THRESHOLD:
                    flagged += 1

            processed += 1

    print(f"Processed: {processed} | Skipped: {skipped} | No name map: {no_map}")
    print(f"Value bets flagged: {flagged}")

    with engine.connect() as conn:
        top = conn.execute(text("""
            SELECT m.home_team, m.away_team, m.sport_key,
                   e.bet_on, e.best_odds, e.model_prob,
                   e.implied_prob, e.expected_value, e.edge,
                   m.commence_time
            FROM ev_bets e
            JOIN matches m ON e.match_id = m.id
            WHERE e.expected_value > 0.02
              AND e.edge > 0.03
            ORDER BY e.expected_value DESC
            LIMIT 15
        """)).fetchall()

        print(f"\n── Top value bets ──────────────────────────────────────")
        if top:
            print(f"{'Match':<32} {'Bet':<10} {'Odds':<6} "
                  f"{'Model':<8} {'Impl':<8} {'EV':<8} Edge")
            print("─" * 82)
            for r in top:
                match_str = f"{r[0][:14]} vs {r[1][:13]}"
                print(f"{match_str:<32} {r[3]:<10} {float(r[4]):<6.2f} "
                      f"{float(r[5]):<8.1%} {float(r[6]):<8.1%} "
                      f"{float(r[7]):<8.4f} {float(r[8]):.4f}")
        else:
            print("No strong value bets found above threshold.")

    print(f"\nDone — {datetime.now():%H:%M:%S}")

if __name__ == '__main__':
    run()