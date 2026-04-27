import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useParams, useNavigate, Outlet } from 'react-router-dom';
import axios from 'axios';
import { Search, RefreshCw, CheckCircle, XCircle, AlertCircle, Shield, Home, Activity, Tv } from 'lucide-react';

function StaffDashboard() {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);

  const fetchDashboard = () => {
    setLoading(true);
    axios.get('/api/dashboard')
      .then(res => {
        setData(res.data.reservations || {});
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const [syncing, setSyncing] = useState(false);

  const triggerSync = () => {
    setSyncing(true);
    axios.post('/api/trigger_sync').then(() => {
      setTimeout(() => {
        setSyncing(false);
        fetchDashboard();
      }, 2000);
    });
  };

  const reservations = Object.values(data);
  const total = reservations.length;
  let errorCount = 0;
  reservations.forEach(r => {
    r.riders.forEach(rider => {
      if (!rider.is_child && (rider.mpowr_status === "Missing Waiver" || rider.tripworks_status === "Missing Waiver")) {
        errorCount++;
      }
    });
  });

  return (
    <div className="view-container">
      <header className="dash-header">
        <div>
          <h2>Live Staff Dashboard</h2>
          <p className="subtitle">Real-time discrepancy insights</p>
        </div>
        <button onClick={triggerSync} className="btn-primary" disabled={syncing} style={{ opacity: syncing ? 0.7 : 1 }}>
          <RefreshCw size={16} className={syncing ? "rotate-anim" : ""} /> {syncing ? "Syncing Network..." : "Force Sync"}
        </button>
      </header>

      <div className="metrics-row">
        <div className="metric-card">
          <h3>Total Reservations</h3>
          <p className="metric-value">{total}</p>
        </div>
        <div className="metric-card error-card">
          <h3>Waiver Flags</h3>
          <p className="metric-value color-danger">{errorCount}</p>
        </div>
      </div>

      <div className="reservation-grid">
        {loading ? <p>Loading data...</p> : reservations.map(res => (
          <div key={res.reservation_id} className="res-card">
            <div className="res-card-header">
              <h3>{res.reservation_id}</h3>
              <span className="badge">Expected: {res.expected_waiver_count}</span>
            </div>
            <div className="riders-list">
              {res.riders.map((rider, idx) => (
                <div key={idx} className="rider-row">
                  <span className="rider-name">{rider.name} {rider.is_child && "🧒"}</span>
                  <div className="statuses">
                    <span className={`status-badge ${rider.mpowr_status === "Missing Waiver" ? 'danger' : 'success'}`}>
                      MPOWR: {rider.mpowr_status === "Missing Waiver" ? <XCircle size={14}/> : <CheckCircle size={14}/>}
                    </span>
                    <span className={`status-badge ${rider.tripworks_status === "Missing Waiver" ? 'danger' : 'success'}`}>
                      Epic: {rider.tripworks_status === "Missing Waiver" ? <XCircle size={14}/> : <CheckCircle size={14}/>}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
        {!loading && total === 0 && (
          <div className="empty-state">No reservations flagged or tracked today.</div>
        )}
      </div>
    </div>
  );
}

function CustomerSearch() {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  const handleSearch = (e) => {
    e.preventDefault();
    if(query.trim()) {
      navigate(`/customer/${query.trim()}`);
    }
  };

  return (
    <div className="customer-portal-container res-card">
      <div className="portal-header" style={{textAlign: "center", marginBottom: "2rem"}}>
        <Shield size={48} style={{color: "var(--epic-red)", marginBottom: "1rem"}} />
        <h2>Waiver Lookup Portal</h2>
        <p className="subtitle">Enter your Epic 4x4 Confirmation ID.</p>
      </div>
      <form onSubmit={handleSearch} className="search-bar" style={{display: "flex", gap: "1rem"}}>
        <Search size={20} style={{alignSelf: "center", position: "absolute", marginLeft: "10px", color: "var(--text-muted)"}} />
        <input 
          type="text" 
          value={query} 
          onChange={(e) => setQuery(e.target.value)} 
          placeholder="e.g., CO-GP8" 
          autoFocus
          style={{padding: "1rem 1rem 1rem 2.5rem", width: "100%", borderRadius: "6px", border: "1px solid var(--border-color)", fontSize: "1rem"}}
        />
        <button type="submit" className="btn-primary">Track</button>
      </form>
    </div>
  );
}

function CustomerUniqueLink() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`/api/customer/status?query=${id}`)
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(err => {
        setError("Could not locate reservation. Please check your ID and try again.");
        setLoading(false);
      });
  }, [id]);

  if (loading) return <div>Locating your waivers...</div>;
  if (error || !data) return <div className="res-card color-danger">{error || "Not found."}</div>;

  return (
    <div className="customer-portal-container res-card">
      <div style={{textAlign: "center", marginBottom: "2rem"}}>
        <h2>Your Epic 4x4 Waivers</h2>
        <p className="subtitle">Reservation: <strong>{data.reservation_id}</strong></p>
      </div>
      <div className="riders-list">
        {data.riders.map((rider, idx) => (
          <div key={idx} className="rider-row">
            <div>
              <span className="rider-name">{rider.name}</span>
            </div>
            <div className="statuses">
              <span className={`status-badge ${rider.mpowr_status === "Missing Waiver" ? 'danger' : 'success'}`}>
                Polaris: {rider.mpowr_status === "Missing Waiver" ? 'Pending' : 'Done'}
              </span>
              <span className={`status-badge ${rider.tripworks_status === "Missing Waiver" ? 'danger' : 'success'}`}>
                Epic 4x4: {rider.tripworks_status === "Missing Waiver" ? 'Pending' : 'Done'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ========================================= */
/* THE ISOLATED TV DASHBOARD VIEW            */
/* ========================================= */
function TVDashboard() {
  const [reservations, setReservations] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

  const fetchTVData = () => {
    axios.get('/api/dashboard').then(res => {
      const data = res.data.reservations || {};
      const allRes = Object.values(data);
      
      const todayString = new Date().toDateString();
      // Filter strictly for today's reservations based on start_date
      const todaysTrips = allRes.filter(r => {
        if (!r.start_date) return true; // Fallback if no date loaded
        return new Date(r.start_date).toDateString() === todayString;
      });
      setReservations(todaysTrips);
    }).catch(console.error);
  };

  useEffect(() => {
    fetchTVData();
    // Auto refresh data every 60 seconds
    const interval = setInterval(fetchTVData, 60000);
    // Auto refresh local clock every second
    const clockInt = setInterval(() => setCurrentTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })), 1000);
    
    return () => {
      clearInterval(interval);
      clearInterval(clockInt);
    };
  }, []);

  return (
    <div className="tv-layout">
      <header className="tv-header">
        <div className="epic-logo-wrapper tv-size">
          <div className="epic-logo-top">
            <span className="epic-logo-red">EPIC</span>
            <span className="epic-logo-black" style={{color: '#FFF'}}>4</span>
            <span className="epic-logo-red">x</span>
            <span className="epic-logo-black" style={{color: '#FFF'}}>4</span>
          </div>
          <div className="epic-logo-bottom" style={{color: '#AAA'}}>ADVENTURES</div>
        </div>
        <div className="tv-clock">{currentTime}</div>
      </header>
      
      <main className="tv-main">
        {reservations.length === 0 ? (
          <div className="tv-empty">No departures remaining for today.</div>
        ) : (
          <div className="tv-grid">
            {reservations.map(res => {
              const expected = res.expected_waiver_count;
              // Calculate fractions
              let polarisComplete = 0;
              let epicComplete = 0;
              res.riders.forEach(r => {
                // Determine completion counting logic. Assumes 1 waiver per rider technically.
                if (r.mpowr_status === "Completed Waiver") polarisComplete++;
                if (r.tripworks_status === "Completed Waiver") epicComplete++;
              });
              
              // Fallback logic in case data format varies: cap completed to expected visually?
              if (polarisComplete > expected) polarisComplete = expected;
              if (epicComplete > expected) epicComplete = expected;

              const polarisDone = polarisComplete >= expected;
              const epicDone = epicComplete >= expected;

              // Primary Rider name used as Party Name
              const partyName = res.riders[0] ? res.riders[0].name : res.reservation_id;

              return (
                <div key={res.reservation_id} className="tv-card">
                  <div className="tv-party-group">
                    <div className="tv-party-name">{partyName} Party</div>
                    <div className="tv-party-meta">ID: {res.reservation_id} • Party of {expected}</div>
                  </div>
                  
                  <div className="tv-metrics">
                    <div className="tv-metric-box">
                      <div className="tv-metric-label">Polaris Waivers</div>
                      <div className={`tv-metric-value ${polarisDone ? 'success' : 'danger'}`}>
                        {polarisComplete}/{expected}
                      </div>
                    </div>
                    
                    <div className="tv-metric-box">
                      <div className="tv-metric-label">Epic Waivers</div>
                      <div className={`tv-metric-value ${epicDone ? 'success' : 'danger'}`}>
                        {epicComplete}/{expected}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

/* ========================================= */
/* LAYOUT ROUTER SHELLS                      */
/* ========================================= */

// Standard layout with sidebar for staff/customer portals
function StandardLayout() {
  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="logo-container">
          <div className="epic-logo-wrapper">
            <div className="epic-logo-top">
              <span className="epic-logo-red">EPIC</span>
              <span className="epic-logo-black" style={{color: '#FFF'}}>4</span>
              <span className="epic-logo-red">x</span>
              <span className="epic-logo-black" style={{color: '#FFF'}}>4</span>
            </div>
            <div className="epic-logo-bottom" style={{color: '#999'}}>ADVENTURES</div>
          </div>
        </div>
        <ul className="nav-links">
          <li><a href="/staff" className="nav-item"><Activity size={18}/> Staff Dashboard</a></li>
          <li><a href="/customer" className="nav-item"><Search size={18}/> Customer Search</a></li>
          <li style={{marginTop: "2rem"}}><a href="/tv" className="nav-item"><Tv size={18}/> Launch TV Board</a></li>
        </ul>
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <Routes>
        {/* Completely isolated route for the full-screen TV view */}
        <Route path="/tv" element={<TVDashboard />} />
        
        {/* Standard wrapped routes sharing the sidebar */}
        <Route element={<StandardLayout />}>
          <Route path="/" element={<StaffDashboard />} />
          <Route path="/staff" element={<StaffDashboard />} />
          <Route path="/customer" element={<CustomerSearch />} />
          <Route path="/customer/:id" element={<CustomerUniqueLink />} />
        </Route>
      </Routes>
    </Router>
  );
}
