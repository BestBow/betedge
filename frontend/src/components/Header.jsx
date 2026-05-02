export default function Header({ lastUpdate, onRefresh }) {
    return (
      <div style={{
        background: '#0d0d1a',
        borderBottom: '1px solid #1a1a2e',
        padding: '0.75rem 1.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{
            color: '#00ff88', fontSize: 15, fontWeight: 700,
            letterSpacing: '0.15em'
          }}>
            BETEDGE
          </span>
          <span style={{
            color: '#333', fontSize: 10,
            letterSpacing: '0.08em'
          }}>
            MARKET INEFFICIENCY DETECTOR
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {lastUpdate && (
            <span style={{ color: '#444', fontSize: 10 }}>
              UPDATED {lastUpdate}
            </span>
          )}
          <button onClick={onRefresh} style={{
            background: 'none', border: '1px solid #2a2a3e',
            color: '#666', fontFamily: 'inherit', fontSize: 10,
            padding: '4px 10px', borderRadius: 4, cursor: 'pointer',
            letterSpacing: '0.08em',
          }}>
            REFRESH
          </button>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: '#00ff88',
            boxShadow: '0 0 6px #00ff88',
          }} />
        </div>
      </div>
    );
  }