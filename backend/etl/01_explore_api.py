import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv('ODDS_API_KEY')
BASE_URL = 'https://api.the-odds-api.com/v4'

def get(endpoint, params={}):
    params['apiKey'] = API_KEY
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params)
    print(f"Requests remaining: {resp.headers.get('x-requests-remaining', 'N/A')}")
    resp.raise_for_status()
    return resp.json()

# Step 1: What sports are available?
print("=" * 55)
print("AVAILABLE SPORTS")
print("=" * 55)
sports = get('sports')
for s in sports:
    if s.get('active'):
        print(f"  {s['key']:<40} {s['title']}")

# Step 2: Get live odds for soccer EPL
print("\n" + "=" * 55)
print("SAMPLE ODDS — EPL")
print("=" * 55)
try:
    odds = get('sports/soccer_epl/odds', {
        'regions':  'uk',
        'markets':  'h2h',
        'oddsFormat': 'decimal'
    })
    print(f"Matches found: {len(odds)}")
    if odds:
        sample = odds[0]
        print(f"\nSample match: {sample['home_team']} vs {sample['away_team']}")
        print(f"Commence time: {sample['commence_time']}")
        print(f"Bookmakers: {len(sample['bookmakers'])}")
        if sample['bookmakers']:
            bm = sample['bookmakers'][0]
            print(f"\nBookmaker: {bm['title']}")
            for market in bm['markets']:
                print(f"  Market: {market['key']}")
                for outcome in market['outcomes']:
                    implied_prob = 1 / outcome['price']
                    print(f"    {outcome['name']:<20} odds: {outcome['price']}  implied: {implied_prob:.1%}")
except Exception as e:
    print(f"EPL error: {e}")

# Step 3: Check NFL
print("\n" + "=" * 55)
print("SAMPLE ODDS — NFL")
print("=" * 55)
try:
    nfl = get('sports/americanfootball_nfl/odds', {
        'regions':  'us',
        'markets':  'h2h',
        'oddsFormat': 'decimal'
    })
    print(f"NFL matches found: {len(nfl)}")
    if nfl:
        print(f"Sample: {nfl[0]['home_team']} vs {nfl[0]['away_team']}")
except Exception as e:
    print(f"NFL: {e}")

# Step 4: Check NBA
print("\n" + "=" * 55)
print("SAMPLE ODDS — NBA")
print("=" * 55)
try:
    nba = get('sports/basketball_nba/odds', {
        'regions':  'us',
        'markets':  'h2h',
        'oddsFormat': 'decimal'
    })
    print(f"NBA matches found: {len(nba)}")
    if nba:
        print(f"Sample: {nba[0]['home_team']} vs {nba[0]['away_team']}")
except Exception as e:
    print(f"NBA: {e}")

    # Step 5: Check historical odds
print("\n" + "=" * 55)
print("HISTORICAL ODDS — EPL")
print("=" * 55)
try:
    hist = get('sports/soccer_epl/odds-history', {
        'regions':    'uk',
        'markets':    'h2h',
        'oddsFormat': 'decimal',
        'date':       '2024-12-01T00:00:00Z'
    })
    print(f"Historical matches found: {len(hist)}")
    if hist:
        print(f"Sample: {hist[0]['home_team']} vs {hist[0]['away_team']}")
        print(f"Date: {hist[0]['commence_time']}")
except Exception as e:
    print(f"Historical: {e}")

print("\nDone — check requests remaining above.")