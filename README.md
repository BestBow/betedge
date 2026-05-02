# BetEdge: Betting Market Inefficiency Detector

A live sports betting market inefficiency detector that ingests real-time odds across 9 sports via the OddsAPI, compares bookmaker implied probabilities against calibrated Gradient Boosting ML model predictions, and surfaces positive expected value bets on a dark-themed trading terminal dashboard.

<img width="1459" height="804" alt="Screenshot 2026-05-03 at 1 43 20 AM" src="https://github.com/user-attachments/assets/b576b0a0-1ec4-487b-879e-b22bc3eeac9d" />

---

## The Core Idea

Betting markets are theoretically efficient — but they're not. Bookmakers build in a margin (the "vig") and systematically misprice certain outcomes. This system:

1. Fetches live odds from 20+ bookmakers across 9 sports
2. Removes the vig to extract true implied probabilities
3. Compares them against our ML model's calibrated probability estimates
4. Flags bets where our model disagrees with the market by a meaningful margin
5. Computes Expected Value: `EV = (model_prob × profit) − (1 − model_prob) × stake`

When EV > 0, the bet has positive expected value — the market is mispriced in our favor.

---

## Architecture

```
OddsAPI → ETL Pipeline → PostgreSQL → FastAPI → React Dashboard
                ↑
    ML Models (club + international)
    trained on 22K+ historical matches
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Odds ingestion | OddsAPI (9 sports, 20+ bookmakers) |
| ETL pipeline | Python, requests, pandas, SQLAlchemy |
| Database | PostgreSQL (Supabase in production) |
| ML models | Gradient Boosting, probability calibration (scikit-learn) |
| EV calculator | Custom devigging + expected value engine |
| Backend API | FastAPI, Pydantic |
| AI narratives | Claude API (Anthropic) |
| Frontend | React, Recharts |
| Deployment | Render (API), Vercel (frontend), Supabase (DB) |

---

## Models

### Club Football Model
- Trained on 22,592 matches from 11 European leagues (2008–2016)
- Features: recent form, avg goals scored/conceded, head-to-head win rate, team build-up speed, defence pressure, market implied probabilities
- Calibrated using isotonic regression to produce reliable probability estimates
- Accuracy: 52.8% | Brier score: 0.2117 (random baseline: 0.25)

### International Football Model
- Trained on 15,704 international matches (2010–2026)
- Features: FIFA ranking differential, recent form, head-to-head win rate, avg goals, neutral venue flag, tournament weight
- Accuracy: 58.8% | Brier score: 0.1921

### Why calibration matters
Raw model probabilities are often overconfident. Isotonic regression calibration ensures that when the model says 60%, teams actually win ~60% of the time. This is critical for accurate EV calculation — uncalibrated probabilities produce misleading EV signals.

---

## Key Features

### Live ETL Pipeline
Ingests odds from 9 sports across 20+ bookmakers every few hours. Each run stores a permanent snapshot of odds to PostgreSQL — building a historical odds database from day one that enables backtesting over time.

### Devigging Algorithm
Removes bookmaker margin from raw odds to extract true implied probabilities. A bet with decimal odds of 2.00 implies 50% — but after removing a typical 5% vig, the true implied probability is closer to 47.6%.

### EV Calculator
Compares model probabilities against devigged implied probabilities. Flags bets with EV > 2% and edge > 2% as positive value opportunities.

### Trading Terminal Dashboard
Dark-themed React dashboard with live sport filter tabs, value bets table ranked by EV, model vs market scatter plot, and upcoming matches panel. Auto-refreshes every 60 seconds.

---

## Results (live snapshot)

| Metric | Value |
|---|---|
| Matches tracked | 122 |
| Value bets flagged | 63 |
| Average EV | +17.4% |
| Top edge | +23.7% (Burnley home win vs implied 18.2%) |
| Sports covered | 9 |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Server status and model accuracy |
| `GET /api/stats` | Aggregated KPIs |
| `GET /api/value-bets` | Ranked value bets with EV, edge, bookmaker |
| `GET /api/matches` | Upcoming matches with best EV per match |
| `POST /api/analyze` | Analyze a specific match with Claude AI narrative |

---

## Project Structure

```
betedge/
├── backend/
│   ├── etl/
│   │   ├── schema.sql               # PostgreSQL schema and views
│   │   ├── 01_explore_api.py        # OddsAPI exploration
│   │   ├── 02_ingest_odds.py        # Live odds ETL pipeline
│   │   └── 03_compute_ev.py         # EV calculator
│   ├── model/
│   │   ├── 01_train_soccer_model.py # International football model
│   │   ├── 02_train_club_model.py   # Club football model
│   │   └── 03_team_mapper.py        # OddsAPI to dataset name mapping
│   └── api/
│       └── main.py                  # FastAPI backend
├── frontend/
│   └── src/
│       ├── App.js
│       └── components/
│           ├── Header.jsx
│           ├── StatsBar.jsx
│           ├── ValueBets.jsx
│           ├── EVChart.jsx
│           └── MatchList.jsx
├── data/
│   └── raw/                         # Dataset files (not committed)
├── .env.example
└── README.md
```

---

## Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 15
- Node.js 18+
- OddsAPI key (free at the-odds-api.com)
- Anthropic API key (free credits at console.anthropic.com)

### 1. Clone and install

```bash
git clone https://github.com/BestBow/betedge.git
cd betedge
python -m venv venv
source venv/bin/activate
pip install requests pandas numpy scikit-learn fastapi uvicorn \
    python-dotenv anthropic supabase psycopg2-binary sqlalchemy \
    matplotlib seaborn xgboost
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in ODDS_API_KEY, ANTHROPIC_API_KEY, and PostgreSQL credentials
```

### 3. Set up the database

```bash
psql -U postgres -c "CREATE DATABASE betedge;"
psql -U postgres -d betedge -f backend/etl/schema.sql
```

### 4. Download datasets

Place these files in `data/raw/`:
- `results.csv` — Kaggle: "International football results" by Mart Jurisoo
- `fifa_ranking-*.csv` — Kaggle: "FIFA World Ranking 1992-2024"
- `database.sqlite` — Kaggle: "European Soccer Database" by Hugo Mathien

### 5. Train models

```bash
python backend/model/01_train_soccer_model.py
python backend/model/02_train_club_model.py
python backend/model/03_team_mapper.py
```

### 6. Run ETL and compute EV

```bash
python backend/etl/02_ingest_odds.py
python backend/etl/03_compute_ev.py
```

### 7. Start the API

```bash
uvicorn backend.api.main:app --reload --port 8000
```

### 8. Start the dashboard

```bash
cd frontend
npm install
npm start
```

Open `http://localhost:3000`

---

## Disclaimer

This project is built for educational and portfolio purposes to demonstrate ML, data engineering, and full-stack development skills. It is not financial or betting advice. Always gamble responsibly.

---

## Tech Skills Demonstrated

Python, SQL, PostgreSQL, scikit-learn, Gradient Boosting, probability calibration, expected value theory, REST API ingestion, ETL pipeline design, FastAPI, React, Recharts, Supabase, Render, Vercel, Claude API integration
