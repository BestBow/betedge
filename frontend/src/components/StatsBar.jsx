export default function StatsBar({ stats }) {
    if (!stats) return null;
  
    const items = [
      { label: 'MATCHES TRACKED',  value: stats.total_upcoming_matches, color: '#e2e8f0' },
      { label: 'VALUE BETS',       value: stats.value_bets_flagged,     color: '#00ff88' },
      { label: 'AVG EV',           value: `+${(stats.avg_ev * 100).toFixed(1)}%`, color: '#00ff88' },
      { label: 'TOP EDGE',         value: `+${(stats.top_edge * 100).toFixed(1)}%`, color: '#7c6cfa' },
      { label: 'SPORTS COVERED',   value: stats.sports_covered,         color: '#e2e8f0' },
      { label: 'CLUB MODEL ACC',   value: stats.club_model_accuracy,    color: '#888' },
      { label: 'INTL MODEL ACC',   value: stats.soccer_model_accuracy,  color: '#888' },
    ];
  
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 8,
      }}>
        {items.map(item => (
          <div key={item.label} style={{
            background: '#0d0d1a',
            border: '1px solid #1a1a2e',
            borderRadius: 8,
            padding: '0.75rem 1rem',
          }}>
            <div style={{
              fontSize: 9, fontWeight: 600, letterSpacing: '0.1em',
              color: '#444', marginBottom: 6, textTransform: 'uppercase'
            }}>
              {item.label}
            </div>
            <div style={{
              fontSize: 20, fontWeight: 700, color: item.color,
              fontVariantNumeric: 'tabular-nums',
            }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
    );
  }