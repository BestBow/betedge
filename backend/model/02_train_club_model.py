import os
import sqlite3
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, log_loss, brier_score_loss
from sklearn.preprocessing import LabelEncoder
from sklearn.calibration import calibration_curve

print("Loading club match data...")

conn = sqlite3.connect('data/raw/database.sqlite')

# ── Load matches with team names ──────────────────────────────
matches = pd.read_sql("""
    SELECT
        m.id, m.date, m.season,
        m.home_team_api_id, m.away_team_api_id,
        m.home_team_goal, m.away_team_goal,
        l.name as league,
        ht.team_long_name as home_team,
        at.team_long_name as away_team,
        m.B365H, m.B365D, m.B365A
    FROM Match m
    JOIN League l  ON m.league_id  = l.id
    JOIN Team ht   ON m.home_team_api_id = ht.team_api_id
    JOIN Team at   ON m.away_team_api_id = at.team_api_id
    WHERE m.home_team_goal IS NOT NULL
      AND m.away_team_goal IS NOT NULL
      AND m.B365H IS NOT NULL
      AND m.B365D IS NOT NULL
      AND m.B365A IS NOT NULL
""", conn)

# ── Load team attributes ──────────────────────────────────────
team_attrs = pd.read_sql("""
    SELECT team_api_id, date,
           buildUpPlaySpeed, defencePressure,
           defenceAggression, defenceTeamWidth,
           chanceCreationShooting
    FROM Team_Attributes
    WHERE buildUpPlaySpeed IS NOT NULL
""", conn)
conn.close()

team_attrs['date'] = pd.to_datetime(team_attrs['date'])
matches['date']    = pd.to_datetime(matches['date'])

print(f"Matches with odds: {len(matches):,}")
print(f"Date range: {matches['date'].min().date()} to {matches['date'].max().date()}")
print(f"Leagues: {matches['league'].nunique()}")

# ── Outcome ───────────────────────────────────────────────────
def get_outcome(row):
    if row['home_team_goal'] > row['away_team_goal']:
        return 'home_win'
    elif row['home_team_goal'] == row['away_team_goal']:
        return 'draw'
    return 'away_win'

matches['outcome'] = matches.apply(get_outcome, axis=1)
print(f"\nOutcome distribution:\n{matches['outcome'].value_counts()}")

# ── Feature helpers ───────────────────────────────────────────
def get_team_attr(team_id, date, attrs_df, col):
    rows = attrs_df[
        (attrs_df['team_api_id'] == team_id) &
        (attrs_df['date'] <= date)
    ]
    if rows.empty:
        return 50.0
    return float(rows.sort_values('date').iloc[-1][col])

def get_recent_form(team_id, date, matches_df, n=6):
    past = matches_df[matches_df['date'] < date]
    home = past[past['home_team_api_id'] == team_id].copy()
    away = past[past['away_team_api_id'] == team_id].copy()
    home['won'] = (home['home_team_goal'] > home['away_team_goal']).astype(int)
    away['won'] = (away['away_team_goal'] > away['home_team_goal']).astype(int)
    home['pts'] = home.apply(lambda r: 3 if r['home_team_goal'] > r['away_team_goal']
                             else (1 if r['home_team_goal'] == r['away_team_goal'] else 0), axis=1)
    away['pts'] = away.apply(lambda r: 3 if r['away_team_goal'] > r['home_team_goal']
                             else (1 if r['away_team_goal'] == r['home_team_goal'] else 0), axis=1)
    all_games = pd.concat([
        home[['date','won','pts']],
        away[['date','won','pts']]
    ]).sort_values('date').tail(n)
    if len(all_games) == 0:
        return 0.4, 1.0
    return float(all_games['won'].mean()), float(all_games['pts'].mean())

def get_avg_goals(team_id, date, matches_df, n=6):
    past = matches_df[matches_df['date'] < date]
    home = past[past['home_team_api_id'] == team_id][
        ['date','home_team_goal','away_team_goal']
    ].rename(columns={'home_team_goal':'scored','away_team_goal':'conceded'})
    away = past[past['away_team_api_id'] == team_id][
        ['date','away_team_goal','home_team_goal']
    ].rename(columns={'away_team_goal':'scored','home_team_goal':'conceded'})
    all_g = pd.concat([home, away]).sort_values('date').tail(n)
    if len(all_g) == 0:
        return 1.3, 1.2
    return float(all_g['scored'].mean()), float(all_g['conceded'].mean())

def get_h2h(home_id, away_id, date, matches_df):
    past = matches_df[matches_df['date'] < date]
    h2h  = past[
        ((past['home_team_api_id'] == home_id) & (past['away_team_api_id'] == away_id)) |
        ((past['home_team_api_id'] == away_id) & (past['away_team_api_id'] == home_id))
    ].tail(6)
    if len(h2h) == 0:
        return 0.45
    wins = len(h2h[
        ((h2h['home_team_api_id'] == home_id) & (h2h['home_team_goal'] > h2h['away_team_goal'])) |
        ((h2h['away_team_api_id'] == home_id) & (h2h['away_team_goal'] > h2h['home_team_goal']))
    ])
    return wins / len(h2h)

def remove_vig(h, d, a):
    ih, id_, ia = 1/h, 1/d, 1/a
    total = ih + id_ + ia
    return ih/total, id_/total, ia/total

# ── Build features ────────────────────────────────────────────
print("\nBuilding features...")
rows = []

for i, (_, row) in enumerate(matches.iterrows()):
    if i % 2000 == 0:
        print(f"  {i}/{len(matches)}...")

    hid  = row['home_team_api_id']
    aid  = row['away_team_api_id']
    date = row['date']

    hform, hpts    = get_recent_form(hid, date, matches)
    aform, apts    = get_recent_form(aid, date, matches)
    hscored, hconc = get_avg_goals(hid, date, matches)
    ascored, aconc = get_avg_goals(aid, date, matches)
    h2h            = get_h2h(hid, aid, date, matches)

    # Team attributes
    h_speed = get_team_attr(hid, date, team_attrs, 'buildUpPlaySpeed')
    a_speed = get_team_attr(aid, date, team_attrs, 'buildUpPlaySpeed')
    h_press = get_team_attr(hid, date, team_attrs, 'defencePressure')
    a_press = get_team_attr(aid, date, team_attrs, 'defencePressure')

    # Devigged market probabilities as features
    mh, md, ma = remove_vig(row['B365H'], row['B365D'], row['B365A'])

    rows.append({
        'home_form':         hform,
        'away_form':         aform,
        'form_diff':         hform - aform,
        'home_pts_avg':      hpts,
        'away_pts_avg':      apts,
        'home_avg_scored':   hscored,
        'home_avg_conceded': hconc,
        'away_avg_scored':   ascored,
        'away_avg_conceded': aconc,
        'h2h_home_winrate':  h2h,
        'home_build_speed':  h_speed,
        'away_build_speed':  a_speed,
        'home_defence_press':h_press,
        'away_defence_press':a_press,
        'market_home_prob':  mh,
        'market_draw_prob':  md,
        'market_away_prob':  ma,
        'date':              date,
        'home_team':         row['home_team'],
        'away_team':         row['away_team'],
        'league':            row['league'],
        'outcome':           row['outcome'],
    })

df = pd.DataFrame(rows)
print(f"Feature dataset: {df.shape}")

# ── Encode ────────────────────────────────────────────────────
le = LabelEncoder()
df['outcome_enc'] = le.fit_transform(df['outcome'])
print(f"Classes: {le.classes_}")

FEATURE_COLS = [
    'home_form', 'away_form', 'form_diff',
    'home_pts_avg', 'away_pts_avg',
    'home_avg_scored', 'home_avg_conceded',
    'away_avg_scored', 'away_avg_conceded',
    'h2h_home_winrate',
    'home_build_speed', 'away_build_speed',
    'home_defence_press', 'away_defence_press',
    'market_home_prob', 'market_draw_prob', 'market_away_prob',
]

df = df.sort_values('date').dropna(subset=FEATURE_COLS)
X  = df[FEATURE_COLS]
y  = df['outcome_enc']

# ── Time-based split ──────────────────────────────────────────
split = int(len(df) * 0.80)
X_train, X_test = X.iloc[:split], X.iloc[split:]
y_train, y_test = y.iloc[:split], y.iloc[split:]

print(f"\nTrain: {len(X_train):,} | Test: {len(X_test):,}")
print(f"Test period: {df['date'].iloc[split].date()} to {df['date'].iloc[-1].date()}")

# ── Train ─────────────────────────────────────────────────────
print("\nTraining Gradient Boosting classifier...")
base = GradientBoostingClassifier(
    n_estimators     = 400,
    learning_rate    = 0.05,
    max_depth        = 4,
    min_samples_leaf = 8,
    subsample        = 0.8,
    random_state     = 42,
)
base.fit(X_train, y_train)

# ── Calibrate ─────────────────────────────────────────────────
print("Calibrating...")
from sklearn.frozen import FrozenEstimator
calibrated = CalibratedClassifierCV(FrozenEstimator(base), method='isotonic')
calibrated.fit(X_test, y_test)

# ── Evaluate ──────────────────────────────────────────────────
y_pred = calibrated.predict(X_test)
y_prob = calibrated.predict_proba(X_test)

acc   = accuracy_score(y_test, y_pred)
ll    = log_loss(y_test, y_prob)
hw_idx = list(le.classes_).index('home_win')
brier = brier_score_loss(
    y_test == hw_idx,
    y_prob[:, hw_idx]
)

print(f"\nAccuracy:    {acc:.1%}")
print(f"Log loss:    {ll:.4f}")
print(f"Brier score: {brier:.4f}")

# ── Calibration curve ─────────────────────────────────────────
prob_true, prob_pred = calibration_curve(
    y_test == hw_idx,
    y_prob[:, hw_idx],
    n_bins=10
)
plt.figure(figsize=(8, 6))
plt.plot([0,1],[0,1],'k--', label='Perfect')
plt.plot(prob_pred, prob_true, 'o-', color='#1D9E75',
         label='Club model', linewidth=2)
plt.title('Calibration curve — club football home win')
plt.xlabel('Predicted probability')
plt.ylabel('Actual frequency')
plt.legend()
plt.tight_layout()
plt.savefig('backend/model/club_calibration.png', dpi=150)
plt.show()

# ── Feature importance ────────────────────────────────────────
imp = pd.DataFrame({
    'feature':    FEATURE_COLS,
    'importance': base.feature_importances_
}).sort_values('importance', ascending=False)
print(f"\nTop features:\n{imp.head(10).to_string(index=False)}")

# ── Build team name lookup ────────────────────────────────────
# Map OddsAPI team names to dataset team names
team_names = df[['home_team']].drop_duplicates()\
               .rename(columns={'home_team':'name'})
team_names = pd.concat([
    team_names,
    df[['away_team']].drop_duplicates().rename(columns={'away_team':'name'})
]).drop_duplicates().sort_values('name')

# ── Save ──────────────────────────────────────────────────────
bundle = {
    'model':        calibrated,
    'base_model':   base,
    'label_encoder':le,
    'feature_cols': FEATURE_COLS,
    'accuracy':     acc,
    'log_loss':     ll,
    'brier_score':  brier,
    'sport':        'club_soccer',
    'team_names':   team_names['name'].tolist(),
}

with open('backend/model/club_model.pkl', 'wb') as f:
    pickle.dump(bundle, f)

# Also save features for EV calculator
df[['home_team','away_team','league','date'] + FEATURE_COLS + ['outcome']]\
    .to_csv('data/processed/club_features.csv', index=False)

print(f"\nModel saved to backend/model/club_model.pkl")
print(f"Features saved to data/processed/club_features.csv")
print(f"\nKnown teams in dataset: {len(team_names)}")