import os
import json
import pickle
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from difflib import get_close_matches
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = FastAPI(title="BetEdge API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB ────────────────────────────────────────────────────────
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
with open('backend/model/club_model.pkl', 'rb') as f:
    club_bundle = pickle.load(f)
with open('backend/model/soccer_model.pkl', 'rb') as f:
    soccer_bundle = pickle.load(f)
with open('backend/model/team_mapper.json') as f:
    MANUAL_MAPPINGS = json.load(f)

club_model    = club_bundle['model']
club_le       = club_bundle['label_encoder']
CLUB_FEATURES = club_bundle['feature_cols']
known_teams   = club_bundle['team_names']
soccer_model  = soccer_bundle['model']
soccer_le     = soccer_bundle['label_encoder']

# ── Load data ─────────────────────────────────────────────────
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
           defencePressure, defenceAggression
    FROM Team_Attributes WHERE buildUpPlaySpeed IS NOT NULL
""", conn)
conn.close()

club_df['date']    = pd.to_datetime(club_df['date'])
team_attrs['date'] = pd.to_datetime(team_attrs['date'])

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
    'soccer_france_ligue_one',
]

# ── Helpers ───────────────────────────────────────────────────
def map_team(name):
    if name in MANUAL_MAPPINGS:
        mapped = MANUAL_MAPPINGS[name]
        if mapped in known_teams:
            return mapped
    m = get_close_matches(name, known_teams, n=1, cutoff=0.6)
    return m[0] if m else None

def get_team_id(name):
    rows = club_df[club_df['home_team'] == name]['home_team_api_id']
    if rows.empty:
        rows = club_df[club_df['away_team'] == name]['away_team_api_id']
    return int(rows.iloc[0]) if not rows.empty else None

def get_club_form(name, n=6):
    tid = get_team_id(name)
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
    games = pd.concat([home[['date','won','pts']], away[['date','won','pts']]]).sort_values('date').tail(n)
    if len(games) == 0:
        return 0.4, 1.0
    return float(games['won'].mean()), float(games['pts'].mean())

def get_club_goals(name, n=6):
    tid = get_team_id(name)
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

def get_club_h2h(h, a):
    hid, aid = get_team_id(h), get_team_id(a)
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

def get_attr(name, col):
    tid = get_team_id(name)
    if not tid:
        return 50.0
    rows = team_attrs[team_attrs['team_api_id'] == tid]
    if rows.empty:
        return 50.0
    return float(rows.sort_values('date').iloc[-1][col])

def remove_vig(h, d, a):
    ih, id_, ia = 1/h, 1/d, 1/a
    t = ih + id_ + ia
    return ih/t, id_/t, ia/t

def predict_club(h, a, ho, dr, ao):
    hf, hp = get_club_form(h)
    af, ap = get_club_form(a)
    hs, hc = get_club_goals(h)
    as_, ac = get_club_goals(a)
    h2h    = get_club_h2h(h, a)
    mh, md, ma = remove_vig(ho, dr, ao)
    features = pd.DataFrame([[
        hf, af, hf-af, hp, ap,
        hs, hc, as_, ac, h2h,
        get_attr(h, 'buildUpPlaySpeed'),
        get_attr(a, 'buildUpPlaySpeed'),
        get_attr(h, 'defencePressure'),
        get_attr(a, 'defencePressure'),
        mh, md, ma,
    ]], columns=CLUB_FEATURES)
    probs = club_model.predict_proba(features)[0]
    return {c: float(p) for c, p in zip(club_le.classes_, probs)}

# ── Routes ────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "club_model_accuracy":   f"{club_bundle['accuracy']:.1%}",
        "soccer_model_accuracy": f"{soccer_bundle['accuracy']:.1%}",
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/api/value-bets")
def value_bets(min_ev: float = 0.02, min_edge: float = 0.02, limit: int = 20):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT m.home_team, m.away_team, m.sport_key,
                   m.commence_time,
                   e.bet_on, e.bookmaker, e.best_odds,
                   e.model_prob, e.implied_prob,
                   e.expected_value, e.edge
            FROM ev_bets e
            JOIN matches m ON e.match_id = m.id
            WHERE e.expected_value >= :min_ev
              AND e.edge >= :min_edge
              AND m.commence_time > NOW()
            ORDER BY e.expected_value DESC
            LIMIT :limit
        """), {'min_ev': min_ev, 'min_edge': min_edge, 'limit': limit}).fetchall()

    return [dict(zip([
        'home_team','away_team','sport','commence_time',
        'bet_on','bookmaker','best_odds','model_prob',
        'implied_prob','expected_value','edge'
    ], [
        r[0], r[1], r[2], str(r[3]),
        r[4], r[5], float(r[6]),
        float(r[7]), float(r[8]),
        float(r[9]), float(r[10])
    ])) for r in rows]

@app.get("/api/matches")
def get_matches(sport: str = None, limit: int = 50):
    with engine.connect() as conn:
        sql = """
            SELECT DISTINCT m.id, m.home_team, m.away_team,
                   m.sport_key, m.commence_time,
                   e.expected_value, e.edge, e.bet_on
            FROM matches m
            LEFT JOIN ev_bets e ON m.id = e.match_id
              AND e.expected_value = (
                SELECT MAX(e2.expected_value)
                FROM ev_bets e2 WHERE e2.match_id = m.id
              )
            WHERE m.commence_time > NOW()
        """
        params = {'limit': limit}
        if sport:
            sql += " AND m.sport_key = :sport"
            params['sport'] = sport
        sql += " ORDER BY m.commence_time LIMIT :limit"
        rows = conn.execute(text(sql), params).fetchall()

    return [dict(zip([
        'id','home_team','away_team','sport',
        'commence_time','best_ev','edge','best_bet'
    ], [
        r[0], r[1], r[2], r[3], str(r[4]),
        float(r[5]) if r[5] else None,
        float(r[6]) if r[6] else None,
        r[7]
    ])) for r in rows]

@app.get("/api/stats")
def get_stats():
    with engine.connect() as conn:
        total_matches = conn.execute(
            text("SELECT COUNT(*) FROM matches WHERE commence_time > NOW()")
        ).scalar()
        total_value_bets = conn.execute(
            text("SELECT COUNT(*) FROM ev_bets WHERE expected_value > 0.02")
        ).scalar()
        avg_ev = conn.execute(
            text("SELECT ROUND(AVG(expected_value)::numeric, 4) FROM ev_bets WHERE expected_value > 0")
        ).scalar()
        top_edge = conn.execute(
            text("SELECT ROUND(MAX(edge)::numeric, 4) FROM ev_bets")
        ).scalar()
        sports_covered = conn.execute(
            text("SELECT COUNT(DISTINCT sport_key) FROM matches WHERE commence_time > NOW()")
        ).scalar()

    return {
        "total_upcoming_matches": total_matches,
        "value_bets_flagged":     total_value_bets,
        "avg_ev":                 float(avg_ev) if avg_ev else 0,
        "top_edge":               float(top_edge) if top_edge else 0,
        "sports_covered":         sports_covered,
        "club_model_accuracy":    f"{club_bundle['accuracy']:.1%}",
        "last_updated":           datetime.now().isoformat(),
    }

class AnalyzeRequest(BaseModel):
    home_team:  str
    away_team:  str
    sport_key:  str
    home_odds:  float
    draw_odds:  float = None
    away_odds:  float

@app.post("/api/analyze")
def analyze_match(req: AnalyzeRequest):
    h_mapped = map_team(req.home_team)
    a_mapped = map_team(req.away_team)

    if req.sport_key in CLUB_SPORTS and req.draw_odds and h_mapped and a_mapped:
        probs = predict_club(
            h_mapped, a_mapped,
            req.home_odds, req.draw_odds, req.away_odds
        )
    else:
        if req.draw_odds:
            mh, md, ma = remove_vig(req.home_odds, req.draw_odds, req.away_odds)
            probs = {'home_win': mh, 'draw': md, 'away_win': ma}
        else:
            ih = 1/req.home_odds
            ia = 1/req.away_odds
            t  = ih + ia
            probs = {'home_win': ih/t, 'away_win': ia/t}

    ih = 1/req.home_odds
    ia = 1/req.away_odds
    id_ = 1/req.draw_odds if req.draw_odds else None

    def ev(mp, odds):
        return round((mp * (odds-1)) - (1-mp), 4)

    results = {
        'home_team':      req.home_team,
        'away_team':      req.away_team,
        'home_mapped':    h_mapped,
        'away_mapped':    a_mapped,
        'probabilities':  {k: round(v, 4) for k, v in probs.items()},
        'home_ev':        ev(probs['home_win'], req.home_odds),
        'away_ev':        ev(probs['away_win'], req.away_odds),
        'draw_ev':        ev(probs['draw'], req.draw_odds) if req.draw_odds and 'draw' in probs else None,
        'implied_probs': {
            'home': round(ih, 4),
            'away': round(ia, 4),
            'draw': round(id_, 4) if id_ else None,
        }
    }

    # ── Claude narrative ──────────────────────────────────────
    try:
        client  = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        best_ev = max(results['home_ev'], results['away_ev'])
        best_bet = 'home win' if results['home_ev'] > results['away_ev'] else 'away win'

        prompt = f"""You are a sports betting analyst. Analyze this match concisely.

Match: {req.home_team} vs {req.away_team}
Our model probabilities: Home win {probs['home_win']:.1%} | Draw {probs.get('draw', 0):.1%} | Away win {probs['away_win']:.1%}
Bookmaker implied: Home {ih:.1%} | Away {ia:.1%}
Best value bet: {best_bet} (EV: {best_ev:+.3f})

Write 2 short paragraphs:
1. Match assessment based on the stats
2. Where the value lies and why the market might be wrong

Keep it under 120 words. Be specific and analytical."""

        msg = client.messages.create(
            model      = "claude-sonnet-4-20250514",
            max_tokens = 250,
            messages   = [{"role": "user", "content": prompt}]
        )
        results['narrative'] = msg.content[0].text
    except Exception as e:
        results['narrative'] = f"Analysis unavailable: {str(e)}"

    return results