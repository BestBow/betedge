import { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import StatsBar from './components/StatsBar.jsx';
import ValueBets from './components/ValueBets.jsx';
import MatchList from './components/MatchList.jsx';
import EVChart from './components/EVChart.jsx';
import './App.css';

const API = process.env.REACT_APP_API_URL;

export default function App() {
  const [stats,      setStats]      = useState(null);
  const [valueBets,  setValueBets]  = useState([]);
  const [matches,    setMatches]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [sport,      setSport]      = useState('all');

  const SPORTS = [
    { key: 'all',                       label: 'ALL' },
    { key: 'soccer_epl',                label: 'EPL' },
    { key: 'soccer_spain_la_liga',      label: 'LA LIGA' },
    { key: 'soccer_italy_serie_a',      label: 'SERIE A' },
    { key: 'soccer_germany_bundesliga', label: 'BUNDESLIGA' },
    { key: 'basketball_nba',            label: 'NBA' },
    { key: 'baseball_mlb',              label: 'MLB' },
    { key: 'icehockey_nhl',             label: 'NHL' },
    { key: 'mma_mixed_martial_arts',    label: 'MMA' },
  ];

  const fetchData = async () => {
    try {
      const [s, v, m] = await Promise.all([
        fetch(`${API}/api/stats`).then(r => r.json()),
        fetch(`${API}/api/value-bets?min_ev=0.01&limit=50`).then(r => r.json()),
        fetch(`${API}/api/matches?limit=100`).then(r => r.json()),
      ]);
      setStats(s);
      setValueBets(v);
      setMatches(m);
      setLastUpdate(new Date().toLocaleTimeString());
      setLoading(false);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  const filteredBets = sport === 'all'
    ? valueBets
    : valueBets.filter(b => b.sport === sport);

  const filteredMatches = sport === 'all'
    ? matches
    : matches.filter(m => m.sport === sport);

  if (loading) return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', flexDirection: 'column', gap: 12
    }}>
      <div style={{ color: '#00ff88', fontSize: 13 }}>BETEDGE</div>
      <div style={{ color: '#444', fontSize: 11 }}>initializing models...</div>
    </div>
  );

  return (
    <div className="app">
      <Header lastUpdate={lastUpdate} onRefresh={fetchData} />
      <div className="sport-tabs">
        {SPORTS.map(s => (
          <button
            key={s.key}
            className={`sport-tab ${sport === s.key ? 'active' : ''}`}
            onClick={() => setSport(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="main">
        <StatsBar stats={stats} />
        <div className="grid-main">
          <div className="col-left">
            <ValueBets bets={filteredBets} />
          </div>
          <div className="col-right">
            <EVChart bets={filteredBets} />
            <MatchList matches={filteredMatches} />
          </div>
        </div>
      </div>
    </div>
  );
}