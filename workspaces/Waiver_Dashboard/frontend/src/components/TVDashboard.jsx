/**
 * TVDashboard.jsx — Full-screen TV Arrival Board (V2)
 * 
 * V2 Changes:
 *   - OHV: N/A for tours, fraction for rentals
 *   - Renamed POL → MPWR
 *   - Renamed DEP → PAY
 *   - Rental return time shown in sub-line
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Truck, Mountain, Clock, RefreshCw } from 'lucide-react';
import axios from 'axios';
import StatusIcon, { WaiverFraction, DepositBadge } from './StatusIcon';

function TVRow({ guest, index = 0 }) {
  const isRental = guest.booking_type?.toLowerCase() === 'rental';

  return (
    <div className={`tv-row ${guest.overall_status === 'ready' ? 'ready' : 'not-ready'} animate-slide-up${index % 2 === 1 ? ' alt' : ''}`}>
      <StatusIcon status={guest.overall_status === 'ready' ? 'ready' : 'alert'} />
      <div style={{ fontWeight: 700, fontSize: '1rem', minWidth: 60 }}>
        {guest.activity_time}
        {guest.activity_date && (() => {
          const today = new Date().toISOString().split('T')[0];
          if (guest.activity_date !== today) {
            const d = new Date(guest.activity_date + 'T12:00:00');
            const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            return <span style={{ display: 'block', fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 400 }}>{label}</span>;
          }
          return null;
        })()}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: '1rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {guest.guest_name}
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          {isRental ? (guest.vehicle_model || guest.activity_name) : (guest.activity_name || guest.vehicle_model)} • {guest.party_size}p
          {isRental && guest.rental_return_time && ` • Returns ${guest.rental_return_time}`}
          {guest.rental_status === 'OVERDUE' && <span title="Computed from return time — vehicle not yet marked as returned" style={{ color: 'var(--epic-red)', fontWeight: 700, marginLeft: 6, cursor: 'help' }}>⚠ OVERDUE</span>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>T&C</div>
          <WaiverFraction completed={guest.epic_waivers.completed} expected={guest.epic_waivers.expected} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>MPWR</div>
          <WaiverFraction completed={guest.polaris_waivers.completed} expected={guest.polaris_waivers.expected} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>OHV</div>
          {isRental ? (
            guest.ohv_expected > 0 ? (
              <WaiverFraction completed={guest.ohv_complete} expected={guest.ohv_expected} />
            ) : (
              <StatusIcon status={guest.ohv_uploaded ? 'ready' : 'alert'} size="sm" />
            )
          ) : (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>N/A</span>
          )}
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>PAY</div>
          {guest.deposit_status?.toLowerCase() === 'due' ? (
            <DepositBadge status={guest.deposit_status} />
          ) : (
            <DepositBadge status={guest.deposit_status} />
          )}
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>AA</div>
          {isRental ? (
            guest.adventure_assure?.toLowerCase().includes('upgrade') || guest.adventure_assure?.toLowerCase().includes('paid') || guest.adventure_assure?.toLowerCase().includes('premi') ? (
              <span className="badge badge-ready" style={{ fontSize: '0.65rem', background: 'var(--polaris-blue)', color: '#fff' }}>PREM</span>
            ) : (
              <span className="badge badge-blue" style={{ fontSize: '0.65rem', background: 'var(--bg-deep)', color: 'var(--text-muted)' }}>STND</span>
            )
          ) : (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>N/A</span>
          )}
        </div>
        <div style={{ textAlign: 'center', width: 30 }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>DEP</div>
          {isRental ? (
            guest.adventure_assure?.toLowerCase().includes('premi') || guest.adventure_assure?.toLowerCase().includes('paid') ? (
              <span className="badge badge-neutral" style={{ padding: '0 4px' }}>N/A</span>
            ) : (
              <span className="badge badge-alert" style={{ fontSize: '0.85rem' }}>$</span>
            )
          ) : (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>—</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TVDashboard({ filter = 'all' }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(filter);
  const activeTabRef = useRef(filter);
  const [data, setData] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    setActiveTab(filter);
  }, [filter]);

  // Keep ref in sync so WebSocket handler always sees current tab
  useEffect(() => { activeTabRef.current = activeTab; }, [activeTab]);

  const fetchData = useCallback(async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const endpoint = activeTab === 'rental' ? `${baseUrl}/api/tv/rentals`
        : activeTab === 'tour' ? `${baseUrl}/api/tv/tours`
        : `${baseUrl}/api/tv/all`;
      const res = await axios.get(endpoint);
      setData(res.data);
    } catch (err) {
      console.error('TV data fetch failed:', err);
    }
  }, [activeTab]);

  // If activeTab changes, fetch immediately
  useEffect(() => {
    fetchData();
  }, [activeTab, fetchData]);

  useEffect(() => {
    let ws;
    let reconnectTimer;
    
    const connectWS = () => {
      const wsUrl = import.meta.env.VITE_WS_BASE_URL || `ws://${window.location.host}`;
      ws = new WebSocket(`${wsUrl}/api/ws/arrivals`);
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'init' || msg.type === 'update') {
            // Apply current active tab filter client-side since WebSocket sends 'all'
            const allArrivals = msg.arrivals;
            const currentTab = activeTabRef.current;
            let filtered = allArrivals;
            if (currentTab === 'rental') {
              filtered = {
                ...allArrivals,
                now_next: allArrivals.now_next.filter(g => (g.booking_type || '').toLowerCase() === 'rental'),
                upcoming: allArrivals.upcoming.filter(g => (g.booking_type || '').toLowerCase() === 'rental').slice(0, 30),
              };
            } else if (currentTab === 'tour') {
              filtered = {
                ...allArrivals,
                now_next: allArrivals.now_next.filter(g => (g.booking_type || '').toLowerCase() === 'tour'),
                upcoming: allArrivals.upcoming.filter(g => (g.booking_type || '').toLowerCase() === 'tour').slice(0, 30),
              };
            }
            setData(filtered);
          }
        } catch (e) {
          console.error("Error parsing WS message", e);
        }
      };
      
      ws.onclose = () => {
        reconnectTimer = setTimeout(connectWS, 3000);
      };
      
      ws.onerror = (e) => {
        console.error("WebSocket error", e);
        ws.close();
      };
    };

    connectWS();
    const clockInterval = setInterval(() => setCurrentTime(new Date()), 1000);

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
      clearInterval(clockInterval);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const clockStr = currentTime.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: true,
  });

  return (
    <div className="tv-layout">
      {/* Header */}
      <div className="tv-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
          <img
            src="/E4A_Horizontal_Primary.png"
            alt="Epic 4x4 Adventures"
            style={{ height: '36px', width: 'auto' }}
          />
          <div style={{ height: 24, width: 1, background: 'var(--border-default)' }} />
          <h1 className="font-display" style={{ fontSize: '1.25rem', color: 'var(--polaris-blue)', letterSpacing: '0.15em' }}>
            ARRIVAL READINESS BOARD
          </h1>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-lg)' }}>
          {/* Tabs */}
          <div className="tv-tabs">
            <button
              className={`tv-tab ${activeTab === 'rental' ? 'active' : ''}`}
              onClick={() => navigate('/tv/rentals')}
            >
              <Truck size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              RENTALS
            </button>
            <button
              className={`tv-tab ${activeTab === 'tour' ? 'active' : ''}`}
              onClick={() => navigate('/tv/tours')}
            >
              <Mountain size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              TOURS
            </button>
            <button
              className={`tv-tab ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => navigate('/tv')}
            >
              ALL
            </button>
          </div>

          {/* Clock */}
          <div className="font-display" style={{ fontSize: '1.5rem', color: 'var(--polaris-blue)', letterSpacing: '0.1em' }}>
            {clockStr}
          </div>
        </div>
      </div>

      {/* Two-column grid */}
      <div className="tv-grid">
        {/* NOW/NEXT */}
        <div className="tv-column">
          <div className="section-header">
            <span className="dot" style={{ background: 'var(--epic-red)', boxShadow: '0 0 8px var(--epic-red)' }} />
            <span>NOW / NEXT</span>
            <span style={{ fontSize: '0.65rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              0 – 30 min
            </span>
          </div>
          {data?.now_next?.length > 0 ? (
            data.now_next.map((g, idx) => <TVRow key={g.tw_confirmation} guest={g} index={idx} />)
          ) : (
            <div style={{ padding: 'var(--space-2xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '1.1rem' }}>
              <Clock size={40} style={{ marginBottom: 'var(--space-sm)', opacity: 0.3 }} />
              <p>No arrivals right now</p>
            </div>
          )}
        </div>

        {/* UPCOMING */}
        <div className="tv-column">
          <div className="section-header">
            <span className="dot" />
            <span>UPCOMING</span>
            <span style={{ fontSize: '0.65rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              Next {data?.upcoming?.length || 0} reservations
            </span>
          </div>
          {data?.upcoming?.length > 0 ? (
            data.upcoming.map((g, idx) => <TVRow key={g.tw_confirmation} guest={g} index={idx} />)
          ) : (
            <div style={{ padding: 'var(--space-2xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '1.1rem' }}>
              <p>No upcoming arrivals</p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{
        marginTop: 'auto', paddingTop: 'var(--space-md)', borderTop: '1px solid var(--border-default)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        fontSize: '0.75rem', color: 'var(--text-muted)',
      }}>
        <span>
          <StatusIcon status="ready" size="sm" /> Ready &nbsp;&nbsp;
          <StatusIcon status="alert" size="sm" /> Needs Attention
        </span>
        <span>
          Last refresh: {data?.last_refresh || '--'}
        </span>
      </div>
    </div>
  );
}
