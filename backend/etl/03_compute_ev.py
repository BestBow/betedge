import os
import numpy as np
import pandas as pd
from datetime import datetime
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

def remove_vig(home_odds, away_odds, draw_odds=None):
    """
    Remove bookmaker margin (vig) from odds to get
    true implied probabilities. This is called
    'devigging' — critical for EV calculation.
    """
    implied_home = 1 / home_odds
    implied_away = 1 / away_odds
    implied_draw = 1 / draw_odds if draw_odds else 0

    total = implied_home + implied_away + implied_draw

    true_home = implied_home / total
    true_away = implied_away / total
    true_draw = implied_draw / total if draw_odds else None

    return true_home, true_away, true_draw

def compute_ev(model_prob, decimal_odds):
    """
    Expected Value = (model_prob * profit) - (1 - model_prob) * stake
    Using unit stake of 1.
    """
    profit = decimal_odds - 1
    ev = (model_prob * profit) - ((1 - model_prob) * 1)
    return round(ev, 4)

def compute_edge(model_prob, implied_prob):
    """Edge = how much better our probability is vs market."""
    return round(model_prob - implied_prob, 4)

def get_best_odds_for_match(conn, match_id, home_team, away_team):
    """Get best available odds across all bookmakers for a match."""
    rows = conn.execute(text("""
        SELECT bookmaker, home_odds, away_odds, draw_odds
        FROM odds_snapshots
        WHERE match_id = :match_id
        ORDER BY fetched_at DESC
        LIMIT 50
    """), {'match_id': match_id}).fetchall()

    if not rows:
        return None

    best_home_odds = max(r[1] for r in rows)
    best_away_odds = max(r[2] for r in rows)
    draw_odds_list = [r[3] for r in rows if r[3]]
    best_draw_odds = max(draw_odds_list) if draw_odds_list else None

    best_home_bm = next(r[0] for r in rows if r[1] == best_home_odds)
    best_away_bm = next(r[0] for r in rows if r[2] == best_away_odds)

    return {
        'home_odds':    best_home_odds,
        'away_odds':    best_away_odds,
        'draw_odds':    best_draw_odds,
        'home_bm':      best_home_bm,
        'away_bm':      best_away_bm,
    }

def run():
    print(f"\n{'='*55}")
    print(f"  BetEdge EV Calculator — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*55}\n")

    EV_THRESHOLD  = 0.02
    EDGE_THRESHOLD = 0.03

    flagged = 0
    processed = 0

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ev_bets"))

        matches = conn.execute(text("""
            SELECT DISTINCT m.id, m.sport_key, m.home_team,
                            m.away_team, m.commence_time
            FROM matches m
            JOIN odds_snapshots o ON m.id = o.match_id
            WHERE m.commence_time > NOW()
              AND m.completed = FALSE
            ORDER BY m.commence_time
        """)).fetchall()

        print(f"Processing {len(matches)} upcoming matches...\n")

        for match in matches:
            match_id     = match[0]
            sport_key    = match[1]
            home_team    = match[2]
            away_team    = match[3]
            commence     = match[4]

            odds = get_best_odds_for_match(
                conn, match_id, home_team, away_team
            )
            if not odds:
                continue

            home_odds = float(odds['home_odds'])
            away_odds = float(odds['away_odds'])
            draw_odds = float(odds['draw_odds']) if odds['draw_odds'] else None

            true_home, true_away, true_draw = remove_vig(
                home_odds, away_odds, draw_odds
            )

            is_soccer = 'soccer' in sport_key

            if is_soccer:
                home_model = min(true_home * 1.05, 0.95)
                away_model = max(true_away * 0.95, 0.05)
                draw_model = true_draw
            else:
                home_model = min(true_home * 1.03, 0.95)
                away_model = max(true_away * 0.97, 0.05)
                draw_model = None

            total = home_model + away_model + (draw_model or 0)
            home_model = home_model / total
            away_model = away_model / total

            implied_home = round(1 / home_odds, 4)
            implied_away = round(1 / away_odds, 4)
            implied_draw = round(1 / draw_odds, 4) if draw_odds else None

            bets = [
                ('home_win', home_model, implied_home,
                 home_odds, odds['home_bm']),
                ('away_win', away_model, implied_away,
                 away_odds, odds['away_bm']),
            ]
            if draw_odds and draw_model:
                bets.append(
                    ('draw', draw_model, implied_draw,
                     draw_odds, 'best')
                )

            for bet_on, model_prob, imp_prob, best_odds, bm in bets:
                ev   = compute_ev(model_prob, best_odds)
                edge = compute_edge(model_prob, imp_prob)

                conn.execute(text("""
                    INSERT INTO ev_bets
                        (match_id, bookmaker, bet_on, model_prob,
                         implied_prob, best_odds, expected_value, edge)
                    VALUES
                        (:match_id, :bookmaker, :bet_on, :model_prob,
                         :implied_prob, :best_odds, :ev, :edge)
                """), {
                    'match_id':    match_id,
                    'bookmaker':   bm,
                    'bet_on':      bet_on,
                    'model_prob':  round(model_prob, 4),
                    'implied_prob':imp_prob,
                    'best_odds':   best_odds,
                    'ev':          ev,
                    'edge':        edge,
                })

                if ev > EV_THRESHOLD and edge > EDGE_THRESHOLD:
                    flagged += 1

            processed += 1

    print(f"Matches processed:   {processed}")
    print(f"Value bets flagged:  {flagged} (EV > {EV_THRESHOLD:.0%}, edge > {EDGE_THRESHOLD:.0%})")

    with engine.connect() as conn:
        top = conn.execute(text("""
            SELECT m.home_team, m.away_team, m.sport_key,
                   e.bet_on, e.best_odds, e.model_prob,
                   e.implied_prob, e.expected_value, e.edge
            FROM ev_bets e
            JOIN matches m ON e.match_id = m.id
            WHERE e.expected_value > 0.02
              AND e.edge > 0.03
            ORDER BY e.expected_value DESC
            LIMIT 10
        """)).fetchall()

        print(f"\n── Top value bets right now ────────────────────")
        print(f"{'Match':<35} {'Bet':<10} {'Odds':<6} {'Model':<7} {'Impl':<7} {'EV':<7} {'Edge'}")
        print("─" * 90)
        for row in top:
            match_str = f"{row[0][:15]} vs {row[1][:12]}"
            print(f"{match_str:<35} {row[3]:<10} {float(row[4]):<6.2f} "
                  f"{float(row[5]):<7.1%} {float(row[6]):<7.1%} "
                  f"{float(row[7]):<7.4f} {float(row[8]):.4f}")

        if not top:
            print("No strong value bets found with current baseline model.")
            print("This is expected — the XGBoost model in Week 2 will")
            print("generate better probability estimates.")

    print(f"\nEV calculation complete.")

if __name__ == '__main__':
    run()