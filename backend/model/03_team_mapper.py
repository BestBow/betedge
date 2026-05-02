import pickle
import json
from difflib import get_close_matches

# Load known teams from club model
with open('backend/model/club_model.pkl', 'rb') as f:
    bundle = pickle.load(f)

known_teams = bundle['team_names']

# OddsAPI team names that need mapping to dataset names
MANUAL_MAPPINGS = {
    # EPL
    'Manchester City':          'Manchester City',
    'Manchester United':        'Manchester United',
    'Arsenal':                  'Arsenal',
    'Chelsea':                  'Chelsea',
    'Liverpool':                'Liverpool',
    'Tottenham Hotspur':        'Tottenham Hotspur',
    'Newcastle United':         'Newcastle United',
    'West Ham United':          'West Ham United',
    'Aston Villa':              'Aston Villa',
    'Brighton and Hove Albion': 'Brighton & Hove Albion',
    'Brentford':                'Brentford',
    'Fulham':                   'Fulham',
    'Wolverhampton Wanderers':  'Wolverhampton Wanderers',
    'Everton':                  'Everton',
    'Crystal Palace':           'Crystal Palace',
    'Nottingham Forest':        'Nottingham Forest',
    'Bournemouth':              'Bournemouth',
    'Leicester City':           'Leicester City',
    'Leeds United':             'Leeds United',
    'Burnley':                  'Burnley',
    # La Liga
    'Real Madrid':              'Real Madrid CF',
    'Barcelona':                'FC Barcelona',
    'Atletico Madrid':          'Club Atlético de Madrid',
    'Sevilla':                  'Sevilla FC',
    'Real Sociedad':            'Real Sociedad',
    'Athletic Club':            'Athletic Club de Bilbao',
    'Valencia':                 'Valencia CF',
    'Villarreal':               'Villarreal CF',
    'Betis':                    'Real Betis Balompié',
    'Espanyol':                 'RCD Espanyol de Barcelona',
    'Osasuna':                  'CA Osasuna',
    'Getafe':                   'Getafe CF',
    'Celta Vigo':               'Celta de Vigo',
    'Rayo Vallecano':           'Rayo Vallecano de Madrid',
    'Mallorca':                 'RCD Mallorca',
    'Girona':                   'Girona FC',
    'Alaves':                   'Deportivo Alavés',
    'Las Palmas':               'UD Las Palmas',
    'Cadiz':                    'Cádiz CF',
    'Granada':                  'Granada CF',
    # Serie A
    'Inter Milan':              'Inter',
    'AC Milan':                 'AC Milan',
    'Juventus':                 'Juventus',
    'AS Roma':                  'AS Roma',
    'Lazio':                    'SS Lazio',
    'Napoli':                   'SSC Napoli',
    'Atalanta':                 'Atalanta BC',
    'Fiorentina':               'ACF Fiorentina',
    'Torino':                   'Torino FC',
    'Bologna':                  'Bologna FC 1909',
    'Udinese':                  'Udinese Calcio',
    'Sassuolo':                 'US Sassuolo Calcio',
    'Monza':                    'AC Monza',
    'Lecce':                    'US Lecce',
    'Cagliari':                 'Cagliari Calcio',
    'Frosinone':                'Frosinone Calcio',
    'Hellas Verona':            'Hellas Verona FC',
    'Genoa':                    'Genoa CFC',
    'Salernitana':              'US Salernitana 1919',
    'Empoli':                   'Empoli FC',
    'Parma':                    'Parma Calcio 1913',
    'Como':                     'Como 1907',
    # Bundesliga
    'Bayern Munich':            'FC Bayern Munich',
    'Borussia Dortmund':        'Borussia Dortmund',
    'RB Leipzig':               'RasenBallsport Leipzig',
    'Bayer Leverkusen':         'Bayer 04 Leverkusen',
    'Eintracht Frankfurt':      'Eintracht Frankfurt',
    'Wolfsburg':                'VfL Wolfsburg',
    'VfL Wolfsburg':            'VfL Wolfsburg',
    'Borussia Monchengladbach': "Borussia Mönchengladbach",
    'Union Berlin':             '1. FC Union Berlin',
    'SC Freiburg':              'SC Freiburg',
    'Hoffenheim':               'TSG 1899 Hoffenheim',
    'Mainz 05':                 '1. FSV Mainz 05',
    'Augsburg':                 'FC Augsburg',
    'Werder Bremen':            'SV Werder Bremen',
    'Stuttgart':                'VfB Stuttgart',
    'Bochum':                   'VfL Bochum 1848',
    'Koln':                     '1. FC Köln',
    '1. FC Heidenheim 1846':    '1. FC Heidenheim 1846',
    'Darmstadt 98':             'SV Darmstadt 98',
}

def get_dataset_name(odds_api_name):
    """Map OddsAPI team name to dataset team name."""
    if odds_api_name in MANUAL_MAPPINGS:
        mapped = MANUAL_MAPPINGS[odds_api_name]
        if mapped in known_teams:
            return mapped

    # Try fuzzy match as fallback
    matches = get_close_matches(odds_api_name, known_teams, n=1, cutoff=0.6)
    if matches:
        return matches[0]

    return None

# ── Test the mapper ───────────────────────────────────────────
test_teams = [
    'Manchester City', 'Bayern Munich', 'Real Madrid',
    'Inter Milan', 'Arsenal', 'Juventus',
    'Borussia Dortmund', 'AC Milan', 'Chelsea',
    'Unknown Team FC'
]

print("Team name mapping test:")
print(f"{'OddsAPI name':<35} {'Dataset name':<35} {'Found'}")
print("─" * 80)
found = 0
for team in test_teams:
    mapped = get_dataset_name(team)
    status = '✓' if mapped else '✗'
    if mapped:
        found += 1
    print(f"{team:<35} {str(mapped):<35} {status}")

print(f"\nMapped {found}/{len(test_teams)} test teams")

# Save mapper
with open('backend/model/team_mapper.json', 'w') as f:
    json.dump(MANUAL_MAPPINGS, f, indent=2)
print("Team mapper saved to backend/model/team_mapper.json")