import os
import json
import pickle
#import sqlite3
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
SOCCER_FEATURES = soccer_bundle['feature_cols']
 
# ── Load pre-computed club features ───────────────────────────
club_df = pd.read_csv('data/processed/club_features.csv')
club_df['date'] = pd.to_datetime(club_df['date'])
 
# ── Load FIFA rankings ────────────────────────────────────────
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
 
def get_team_latest_features(team_name):
    """
    Get the most recent pre-computed features for a team
    by looking up their last match as home or away team.
    Returns a dict of feature values.
    """
    home_rows = club_df[club_df['home_team'] == team_name].sort_values('date')
    away_rows = club_df[club_df['away_team'] == team_name].sort_values('date')
 
    # Get most recent row where team played
    all_rows = []
    if not home_rows.empty:
        last_home = home_rows.iloc[-1]
        all_rows.append({
            'date':         last_home['date'],
            'form':         last_home['home_form'],
            'pts_avg':      last_home['home_pts_avg'],
            'avg_scored':   last_home['home_avg_scored'],
            'avg_conceded': last_home['home_avg_conceded'],
            'build_speed':  last_home['home_build_speed'],
            'defence_press':last_home['home_defence_press'],
        })
    if not away_rows.empty:
        last_away = away_rows.iloc[-1]
        all_rows.append({
            'date':         last_away['date'],
            'form':         last_away['away_form'],
            'pts_avg':      last_away['away_pts_avg'],
            'avg_scored':   last_away['away_avg_scored'],
            'avg_conceded': last_away['away_avg_conceded'],
            'build_speed':  last_away['away_build_speed'],
            'defence_press':last_away['away_defence_press'],
        })
 
    if not all_rows:
        return {
            'form': 0.4, 'pts_avg': 1.0,
            'avg_scored': 1.3, 'avg_conceded': 1.2,
            'build_speed': 50.0, 'defence_press': 50.0,
        }
 
    # Return features from most recent match
    return sorted(all_rows, key=lambda x: x['date'])[-1]
 
def get_h2h(home_name, away_name):
    """Get head to head win rate from pre-computed features."""
    h2h_rows = club_df[
        ((club_df['home_team'] == home_name) & (club_df['away_team'] == away_name)) |
        ((club_df['home_team'] == away_name) & (club_df['away_team'] == home_name))
    ].tail(6)
 
    if h2h_rows.empty:
        return 0.45
 
    home_wins = len(h2h_rows[
        ((h2h_rows['home_team'] == home_name) & (h2h_rows['outcome'] == 'home_win')) |
        ((h2h_rows['away_team'] == home_name) & (h2h_rows['outcome'] == 'away_win'))
    ])
    return home_wins / len(h2h_rows)
 
def remove_vig(h, d, a):
    ih, id_, ia = 1/h, 1/d, 1/a
    t = ih + id_ + ia
    return ih/t, id_/t, ia/t
 
def predict_club(home_name, away_name, home_odds, draw_odds, away_odds):
    """Build features from pre-computed CSV and predict."""
    hf = get_team_latest_features(home_name)
    af = get_team_latest_features(away_name)
    h2h = get_h2h(home_name, away_name)
    mh, md, ma = remove_vig(home_odds, draw_odds, away_odds)
 
    features = pd.DataFrame([[
        hf['form'],
        af['form'],
        hf['form'] - af['form'],
        hf['pts_avg'],
        af['pts_avg'],
        hf['avg_scored'],
        hf['avg_conceded'],
        af['avg_scored'],
        af['avg_conceded'],
        h2h,
        hf['build_speed'],
        af['build_speed'],
        hf['defence_press'],
        af['defence_press'],
        mh, md, ma,
    ]], columns=CLUB_FEATURES)
 
    probs = club_model.predict_proba(features)[0]
    return {c: float(p) for c, p in zip(club_le.classes_, probs)}
 
# ── International helpers ─────────────────────────────────────
def get_intl_rank(team):
    rows = rankings[rankings['team'] == team]
    if rows.empty:
        return 100.0
    return float(rows.sort_values('rank_date').iloc[-1]['rank'])
 
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
 
    ih  = 1/req.home_odds
    ia  = 1/req.away_odds
    id_ = 1/req.draw_odds if req.draw_odds else None
 
    def ev(mp, odds):
        return round((mp * (odds-1)) - (1-mp), 4)
 
    results = {
        'home_team':     req.home_team,
        'away_team':     req.away_team,
        'home_mapped':   h_mapped,
        'away_mapped':   a_mapped,
        'probabilities': {k: round(v, 4) for k, v in probs.items()},
        'home_ev':       ev(probs['home_win'], req.home_odds),
        'away_ev':       ev(probs['away_win'], req.away_odds),
        'draw_ev':       ev(probs['draw'], req.draw_odds) if req.draw_odds and 'draw' in probs else None,
        'implied_probs': {
            'home': round(ih, 4),
            'away': round(ia, 4),
            'draw': round(id_, 4) if id_ else None,
        }
    }
 
    try:
        client   = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        best_ev  = max(results['home_ev'], results['away_ev'])
        best_bet = 'home win' if results['home_ev'] > results['away_ev'] else 'away win'
 
        prompt = f"""You are a sports betting analyst. Analyze this match concisely.
 
Match: {req.home_team} vs {req.away_team}
Model probabilities: Home win {probs['home_win']:.1%} | Draw {probs.get('draw', 0):.1%} | Away win {probs['away_win']:.1%}
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