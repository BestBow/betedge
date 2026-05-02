function formatTime(str) {
    if (!str) return '';
    const d = new Date(str);
    return d.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }
  
  export default function MatchList({ matches }) {
    const withEV = matches.filter(m => m.best_ev && m.best_ev > 0.01);
  
    return (
      <div className="card">
        <div className="card-title">
          UPCOMING MATCHES
          <span>{matches.length} tracked</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Match</th>
              <th>Kickoff</th>
              <th>Best Bet</th>
              <th>Best EV</th>
            </tr>
          </thead>
          <tbody>
            {withEV.slice(0, 15).map((m, i) => (
              <tr key={i}>
                <td>
                  <div style={{ color: '#e2e8f0', fontSize: 11 }}>
                    {m.home_team}
                  </div>
                  <div style={{ color: '#555', fontSize: 10 }}>
                    vs {m.away_team}
                  </div>
                </td>
                <td style={{ color: '#555', fontSize: 10 }}>
                  {formatTime(m.commence_time)}
                </td>
                <td style={{
                  color: m.best_bet === 'home_win' ? '#7c6cfa'
                       : m.best_bet === 'away_win' ? '#fa9c6c'
                       : '#888',
                  fontSize: 10, fontWeight: 600,
                }}>
                  {m.best_bet?.replace('_', ' ').toUpperCase() || '—'}
                </td>
                <td style={{
                  color: '#00ff88', fontSize: 11,
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {m.best_ev ? `+${(m.best_ev * 100).toFixed(1)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }