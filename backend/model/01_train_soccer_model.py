import os
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, log_loss, brier_score_loss
from sklearn.preprocessing import LabelEncoder
from dotenv import load_dotenv

load_dotenv()

print("Loading data...")

# ── Load match results ────────────────────────────────────────
raw = pd.read_csv('data/raw/results.csv')
raw['date'] = pd.to_datetime(raw['date'])
raw = raw[raw['date'] >= '2000-01-01'].copy()

# Load FIFA rankings
r1 = pd.read_csv('data/raw/fifa_ranking-2023-07-20.csv')
r2 = pd.read_csv('data/raw/fifa_ranking-2024-04-04.csv')
r3 = pd.read_csv('data/raw/fifa_ranking-2024-06-20.csv')
rankings = pd.concat([r1, r2, r3], ignore_index=True)
rankings = rankings.drop_duplicates(subset=['country_full', 'rank_date'])
rankings['rank_date'] = pd.to_datetime(rankings['rank_date'])
rankings['rank'] = pd.to_numeric(rankings['rank'], errors='coerce')
rankings = rankings.dropna(subset=['rank'])
rankings = rankings.rename(columns={'country_full': 'team'})

# ── Feature helpers ───────────────────────────────────────────
def get_rank(team, date):
    rows = rankings[(rankings['team'] == team) &
                    (rankings['rank_date'] <= date)]
    if rows.empty:
        return 100
    return float(rows.sort_values('rank_date').iloc[-1]['rank'])

def get_form(team, date, df, n=10):
    past = df[df['date'] < date]
    home = past[past['home_team'] == team].copy()
    away = past[past['away_team'] == team].copy()
    home['won'] = (home['home_score'] > home['away_score']).astype(int)
    away['won'] = (away['away_score'] > away['home_score']).astype(int)
    games = pd.concat([
        home[['date','won']], away[['date','won']]
    ]).sort_values('date').tail(n)
    return float(games['won'].mean()) if len(games) > 0 else 0.5

def get_goals(team, date, df, n=10):
    past = df[df['date'] < date]
    home = past[past['home_team'] == team][['date','home_score','away_score']]\
           .rename(columns={'home_score':'scored','away_score':'conceded'})
    away = past[past['away_team'] == team][['date','away_score','home_score']]\
           .rename(columns={'away_score':'scored','home_score':'conceded'})
    games = pd.concat([home, away]).sort_values('date').tail(n)
    if len(games) == 0:
        return 1.5, 1.0
    return float(games['scored'].mean()), float(games['conceded'].mean())

def get_h2h(home, away, date, df):
    past = df[df['date'] < date]
    h2h  = past[
        ((past['home_team'] == home) & (past['away_team'] == away)) |
        ((past['home_team'] == away) & (past['away_team'] == home))
    ].tail(10)
    if len(h2h) == 0:
        return 0.5
    wins = len(h2h[
        ((h2h['home_team'] == home) & (h2h['home_score'] > h2h['away_score'])) |
        ((h2h['away_team'] == home) & (h2h['away_score'] > h2h['home_score']))
    ])
    return wins / len(h2h)

def get_tournament_weight(tournament):
    """Weight matches by importance."""
    t = str(tournament).lower()
    if 'world cup' in t:
        return 3.0
    elif 'champions' in t or 'euro' in t:
        return 2.0
    elif 'friendly' in t:
        return 0.5
    return 1.0

# ── Build features ────────────────────────────────────────────
# Use matches from 2010 onwards
matches = raw[raw['date'] >= '2010-01-01'].copy()
print(f"Building features for {len(matches):,} matches...")

rows = []
for i, (_, row) in enumerate(matches.iterrows()):
    if i % 1000 == 0:
        print(f"  {i}/{len(matches)}...")

    home  = row['home_team']
    away  = row['away_team']
    date  = row['date']

    home_rank  = get_rank(home, date)
    away_rank  = get_rank(away, date)
    home_form  = get_form(home, date, raw)
    away_form  = get_form(away, date, raw)
    h_scored, h_conceded = get_goals(home, date, raw)
    a_scored, a_conceded = get_goals(away, date, raw)
    h2h        = get_h2h(home, away, date, raw)
    t_weight   = get_tournament_weight(row.get('tournament', ''))
    is_neutral = int(row.get('neutral', False))

    # Outcome
    if row['home_score'] > row['away_score']:
        outcome = 'home_win'
    elif row['home_score'] == row['away_score']:
        outcome = 'draw'
    else:
        outcome = 'away_win'

    rows.append({
        'rank_diff':         away_rank - home_rank,
        'home_rank':         home_rank,
        'away_rank':         away_rank,
        'home_form':         home_form,
        'away_form':         away_form,
        'form_diff':         home_form - away_form,
        'h2h_home_winrate':  h2h,
        'home_avg_scored':   h_scored,
        'home_avg_conceded': h_conceded,
        'away_avg_scored':   a_scored,
        'away_avg_conceded': a_conceded,
        'is_neutral':        is_neutral,
        'tournament_weight': t_weight,
        'date':              date,
        'outcome':           outcome,
        'sample_weight':     t_weight,
    })

df = pd.DataFrame(rows).dropna()
print(f"Feature dataset: {df.shape}")

# ── Encode labels ─────────────────────────────────────────────
le = LabelEncoder()
df['outcome_enc'] = le.fit_transform(df['outcome'])
print(f"Classes: {le.classes_}")

FEATURE_COLS = [
    'rank_diff', 'home_rank', 'away_rank',
    'home_form', 'away_form', 'form_diff',
    'h2h_home_winrate',
    'home_avg_scored', 'home_avg_conceded',
    'away_avg_scored', 'away_avg_conceded',
    'is_neutral', 'tournament_weight',
]

df = df.sort_values('date')
X  = df[FEATURE_COLS]
y  = df['outcome_enc']
sw = df['sample_weight']

# ── Time-series split ─────────────────────────────────────────
split = int(len(df) * 0.80)
X_train, X_test = X.iloc[:split], X.iloc[split:]
y_train, y_test = y.iloc[:split], y.iloc[split:]
sw_train        = sw.iloc[:split]

print(f"\nTrain: {len(X_train):,} | Test: {len(X_test):,}")
print(f"Test period: {df['date'].iloc[split].date()} to {df['date'].iloc[-1].date()}")

# ── Train Gradient Boosting ───────────────────────────────────
print("\nTraining Gradient Boosting classifier...")
base_model = GradientBoostingClassifier(
    n_estimators    = 300,
    learning_rate   = 0.05,
    max_depth       = 4,
    min_samples_leaf= 10,
    subsample       = 0.8,
    random_state    = 42,
)
base_model.fit(X_train, y_train, sample_weight=sw_train)

# ── Calibrate probabilities ───────────────────────────────────
# This is the key step — raw model probabilities are often
# overconfident. Calibration makes them reliable.
print("Calibrating probabilities...")
calibrated = CalibratedClassifierCV(base_model, method='isotonic', cv='prefit')
calibrated.fit(X_test, y_test)

# ── Evaluate ──────────────────────────────────────────────────
y_pred      = calibrated.predict(X_test)
y_prob      = calibrated.predict_proba(X_test)

acc         = accuracy_score(y_test, y_pred)
ll          = log_loss(y_test, y_prob)
brier       = brier_score_loss(y_test == le.transform(['home_win'])[0],
                                y_prob[:, le.transform(['home_win'])[0]])

print(f"\nAccuracy:    {acc:.1%}")
print(f"Log loss:    {ll:.4f}  (lower is better)")
print(f"Brier score: {brier:.4f} (lower is better, 0.25 = random)")

# ── Calibration curve ─────────────────────────────────────────
home_win_idx = le.transform(['home_win'])[0]
prob_true, prob_pred = calibration_curve(
    y_test == home_win_idx,
    y_prob[:, home_win_idx],
    n_bins=10
)

plt.figure(figsize=(8, 6))
plt.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
plt.plot(prob_pred, prob_true, 'o-', color='#534AB7',
         label='Calibrated model', linewidth=2)
plt.xlabel('Mean predicted probability')
plt.ylabel('Fraction of positives')
plt.title('Calibration curve — soccer home win probability')
plt.legend()
plt.tight_layout()
plt.savefig('backend/model/calibration_curve.png', dpi=150)
plt.show()
print("Calibration curve saved.")

# ── Feature importance ────────────────────────────────────────
importance = pd.DataFrame({
    'feature':    FEATURE_COLS,
    'importance': base_model.feature_importances_
}).sort_values('importance', ascending=False)
print(f"\nTop features:\n{importance.head(8).to_string(index=False)}")

# ── Save ──────────────────────────────────────────────────────
model_bundle = {
    'model':        calibrated,
    'base_model':   base_model,
    'label_encoder':le,
    'feature_cols': FEATURE_COLS,
    'accuracy':     acc,
    'log_loss':     ll,
    'brier_score':  brier,
    'sport':        'soccer',
}

os.makedirs('backend/model', exist_ok=True)
with open('backend/model/soccer_model.pkl', 'wb') as f:
    pickle.dump(model_bundle, f)

print(f"\nModel saved to backend/model/soccer_model.pkl")