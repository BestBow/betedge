function EVBadge({ ev }) {
    const pct   = (ev * 100).toFixed(1);
    const color = ev > 0.5 ? '#00ff88' : ev > 0.1 ? '#88ffbb' : '#aaa';
    return (
      <span style={{
        background: '#001a0d', color, border: `1px solid ${color}33`,
        padding: '2px 7px', borderRadius: 4, fontSize: 11,
        fontWeight: 600,
      }}>
        +{pct}%
      </span>
    );
  }
  
  function SportBadge({ sport }) {
    const labels = {
      soccer_epl:                'EPL',
      soccer_spain_la_liga:      'LIGA',
      soccer_italy_serie_a:      'SERIE A',
      soccer_germany_bundesliga: 'BL',
      soccer_uefa_champs_league: 'UCL',
      basketball_nba:            'NBA',
      baseball_mlb:              'MLB',
      icehockey_nhl:             'NHL',
      mma_mixed_martial_arts:    'MMA',
    };
    return (
      <span style={{
        background: '#0d0d2a', color: '#7c6cfa',
        border: '1px solid #7c6cfa33',
        padding: '2px 6px', borderRadius: 4,
        fontSize: 9, fontWeight: 600, letterSpacing: '0.06em',
      }}>
        {labels[sport] || sport.split('_').pop().toUpperCase()}
      </span>
    );
  }
  
  export default function ValueBets({ bets }) {
    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-title">
          VALUE BETS
          <span>{bets.length} flagged</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Match</th>
              <th>League</th>
              <th>Bet</th>
              <th>Odds</th>
              <th>Model</th>
              <th>Impl</th>
              <th>EV</th>
              <th>Edge</th>
              <th>Book</th>
            </tr>
          </thead>
          <tbody>
            {bets.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ color: '#444', textAlign: 'center', padding: '2rem' }}>
                  No value bets above threshold
                </td>
              </tr>
            ) : bets.map((bet, i) => (
              <tr key={i}>
                <td style={{ maxWidth: 180 }}>
                  <div style={{ color: '#e2e8f0', fontSize: 11, fontWeight: 500 }}>
                    {bet.home_team}
                  </div>
                  <div style={{ color: '#555', fontSize: 10 }}>
                    vs {bet.away_team}
                  </div>
                </td>
                <td><SportBadge sport={bet.sport} /></td>
                <td>
                  <span style={{
                    color: bet.bet_on === 'home_win' ? '#7c6cfa'
                         : bet.bet_on === 'away_win' ? '#fa9c6c'
                         : '#888',
                    fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
                  }}>
                    {bet.bet_on === 'home_win' ? 'HOME'
                   : bet.bet_on === 'away_win' ? 'AWAY'
                   : 'DRAW'}
                  </span>
                </td>
                <td style={{ color: '#e2e8f0', fontVariantNumeric: 'tabular-nums' }}>
                  {bet.best_odds.toFixed(2)}
                </td>
                <td style={{ color: '#00ff88', fontVariantNumeric: 'tabular-nums' }}>
                  {(bet.model_prob * 100).toFixed(1)}%
                </td>
                <td style={{ color: '#888', fontVariantNumeric: 'tabular-nums' }}>
                  {(bet.implied_prob * 100).toFixed(1)}%
                </td>
                <td><EVBadge ev={bet.expected_value} /></td>
                <td style={{
                  color: '#00ff88', fontVariantNumeric: 'tabular-nums',
                  fontSize: 11,
                }}>
                  +{(bet.edge * 100).toFixed(1)}%
                </td>
                <td style={{ color: '#555', fontSize: 10 }}>
                  {bet.bookmaker?.split(' ')[0]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }