import {
    ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer, ReferenceLine
  } from 'recharts';
  
  export default function EVChart({ bets }) {
    const data = bets
      .filter(b => b.expected_value !== null)
      .map(b => ({
        x:    parseFloat((b.implied_prob * 100).toFixed(1)),
        y:    parseFloat((b.model_prob  * 100).toFixed(1)),
        ev:   b.expected_value,
        name: `${b.home_team} vs ${b.away_team}`,
        bet:  b.bet_on,
      }));
  
    const CustomTooltip = ({ active, payload }) => {
      if (!active || !payload?.length) return null;
      const d = payload[0].payload;
      return (
        <div style={{
          background: '#0d0d1a', border: '1px solid #2a2a3e',
          padding: '8px 12px', borderRadius: 6, fontSize: 11,
        }}>
          <div style={{ color: '#e2e8f0', marginBottom: 4 }}>{d.name}</div>
          <div style={{ color: '#7c6cfa' }}>{d.bet?.replace('_', ' ').toUpperCase()}</div>
          <div style={{ color: '#888' }}>Implied: {d.x}%</div>
          <div style={{ color: '#00ff88' }}>Model: {d.y}%</div>
          <div style={{ color: '#00ff88' }}>EV: +{(d.ev * 100).toFixed(1)}%</div>
        </div>
      );
    };
  
    return (
      <div className="card">
        <div className="card-title">
          MODEL VS MARKET
          <span>scatter — dots above line = value</span>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" />
            <XAxis
              dataKey="x" name="Implied prob"
              tick={{ fontSize: 10, fill: '#444' }}
              label={{ value: 'Implied %', position: 'insideBottom',
                       offset: -5, fill: '#444', fontSize: 10 }}
            />
            <YAxis
              dataKey="y" name="Model prob"
              tick={{ fontSize: 10, fill: '#444' }}
              label={{ value: 'Model %', angle: -90, position: 'insideLeft',
                       fill: '#444', fontSize: 10 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              segment={[{x:0,y:0},{x:100,y:100}]}
              stroke="#333" strokeDasharray="4 4"
            />
            <Scatter
              data={data}
              fill="#00ff88"
              opacity={0.7}
              r={4}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    );
  }