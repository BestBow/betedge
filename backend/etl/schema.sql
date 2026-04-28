-- Sports and leagues
CREATE TABLE IF NOT EXISTS sports (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(100) UNIQUE NOT NULL,
    title       VARCHAR(100) NOT NULL,
    category    VARCHAR(50)
);

-- Teams
CREATE TABLE IF NOT EXISTS teams (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) UNIQUE NOT NULL,
    sport_key   VARCHAR(100)
);

-- Matches
CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    api_id          VARCHAR(100) UNIQUE NOT NULL,
    sport_key       VARCHAR(100) NOT NULL,
    home_team       VARCHAR(150) NOT NULL,
    away_team       VARCHAR(150) NOT NULL,
    commence_time   TIMESTAMP NOT NULL,
    completed       BOOLEAN DEFAULT FALSE,
    home_score      NUMERIC,
    away_score      NUMERIC,
    outcome         VARCHAR(20),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Odds snapshots — stores every time we fetch odds
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker       VARCHAR(100) NOT NULL,
    home_odds       NUMERIC NOT NULL,
    away_odds       NUMERIC NOT NULL,
    draw_odds       NUMERIC,
    fetched_at      TIMESTAMP DEFAULT NOW()
);

-- Model predictions
CREATE TABLE IF NOT EXISTS predictions (
    id                  SERIAL PRIMARY KEY,
    match_id            INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    sport_key           VARCHAR(100),
    home_win_prob       NUMERIC NOT NULL,
    away_win_prob       NUMERIC NOT NULL,
    draw_prob           NUMERIC,
    predicted_outcome   VARCHAR(20),
    model_version       VARCHAR(50),
    created_at          TIMESTAMP DEFAULT NOW()
);

-- EV calculations — the core output
CREATE TABLE IF NOT EXISTS ev_bets (
    id                  SERIAL PRIMARY KEY,
    match_id            INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker           VARCHAR(100),
    bet_on              VARCHAR(20),
    model_prob          NUMERIC,
    implied_prob        NUMERIC,
    best_odds           NUMERIC,
    expected_value      NUMERIC,
    edge                NUMERIC,
    flagged_at          TIMESTAMP DEFAULT NOW()
);

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_results (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(id),
    bet_on          VARCHAR(20),
    odds_used       NUMERIC,
    model_prob      NUMERIC,
    ev_at_bet       NUMERIC,
    outcome         VARCHAR(20),
    won             BOOLEAN,
    profit_loss     NUMERIC,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_matches_sport     ON matches(sport_key);
CREATE INDEX IF NOT EXISTS idx_matches_commence  ON matches(commence_time);
CREATE INDEX IF NOT EXISTS idx_odds_match        ON odds_snapshots(match_id);
CREATE INDEX IF NOT EXISTS idx_ev_value          ON ev_bets(expected_value DESC);
CREATE INDEX IF NOT EXISTS idx_ev_flagged        ON ev_bets(flagged_at DESC);

-- Analytics views
CREATE OR REPLACE VIEW top_value_bets AS
SELECT
    e.id,
    m.home_team,
    m.away_team,
    m.sport_key,
    m.commence_time,
    e.bet_on,
    e.bookmaker,
    e.best_odds,
    e.model_prob,
    e.implied_prob,
    e.expected_value,
    e.edge
FROM ev_bets e
JOIN matches m ON e.match_id = m.id
WHERE m.commence_time > NOW()
  AND e.expected_value > 0
ORDER BY e.expected_value DESC;

CREATE OR REPLACE VIEW backtest_summary AS
SELECT
    sport_key,
    COUNT(*)                            AS total_bets,
    SUM(CASE WHEN won THEN 1 ELSE 0 END) AS wins,
    ROUND(AVG(CASE WHEN won THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate_pct,
    ROUND(SUM(profit_loss)::numeric, 2) AS total_pnl,
    ROUND(AVG(ev_at_bet)::numeric, 4)  AS avg_ev
FROM backtest_results b
JOIN matches m ON b.match_id = m.id
GROUP BY sport_key
ORDER BY total_pnl DESC;