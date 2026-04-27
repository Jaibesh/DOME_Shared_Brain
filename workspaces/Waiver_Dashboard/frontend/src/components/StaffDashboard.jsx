/**
 * StaffDashboard.jsx — Arrival Readiness Board (V2)
 * 
 * V2 Changes:
 *   - Rental/Tour/All filter tabs
 *   - Renamed columns: DEP→PAY, POL→MPWR
 *   - New AA (Adventure Assure) column
 *   - Larger name + vehicle + activity in row layout
 *   - N/A for tours in OHV column, fraction for rentals
 *   - Rental return time in sub-line
 *   - Sort dropdown (Activity Time / Return Time)
 *   - Checked-in split into ON RIDE / RETURNED sub-sections
 *   - Auto-refresh every 60 seconds
 */

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Truck, Mountain, Clock, Users, ArrowUpDown } from 'lucide-react';
import axios from 'axios';
import StatusIcon, { WaiverFraction, DepositBadge } from './StatusIcon';
import DetailFlyout from './DetailFlyout';

function ArrivalRow({ guest, onClick, index = 0 }) {
  const isRental = guest.booking_type?.toLowerCase() === 'rental';
  const isOverdue = guest.rental_status === 'OVERDUE';

  return (
    <div
      className={`arrival-row animate-slide-up${index % 2 === 1 ? ' alt' : ''}`}
      onClick={() => onClick(guest)}
      style={{ animationDelay: '0.05s' }}
    >
      {/* Status dot */}
      <StatusIcon status={guest.checked_in ? 'ready' : guest.overall_status === 'ready' ? 'ready' : 'alert'} size="sm" />

      {/* Time */}
      <span className="time">
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
      </span>

      {/* Guest name + vehicle + activity (V2: larger, in a row) */}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
          <span className="guest-name" style={{ fontSize: '1rem', fontWeight: 700 }}>{guest.guest_name}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--polaris-blue)', fontWeight: 600 }}>{isRental ? (guest.vehicle_model || guest.activity_name) : (guest.activity_name || guest.vehicle_model)}</span>
        </div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ background: 'var(--bg-deep)', padding: '1px 6px', borderRadius: 4, fontSize: '0.7rem', fontWeight: 600 }}>{guest.booking_type}</span>
          <span>{guest.party_size}p</span>
          {isRental && guest.rental_return_time && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              <Clock size={10} /> Returns {guest.rental_return_time}
            </span>
          )}
          {isOverdue && <span title="Computed from return time — vehicle not yet marked as returned" style={{ color: 'var(--epic-red)', fontWeight: 700, fontSize: '0.7rem', cursor: 'help' }}>⚠ OVERDUE</span>}
          {guest.tw_status && guest.tw_status !== 'Not Checked In' && !isOverdue && (
            <span style={{
              fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              color: '#fff',
              background: guest.tw_status === 'Checked In' ? '#16a34a' :
                          guest.tw_status === 'Rental Out' ? '#ea580c' :
                          guest.tw_status === 'No Show' ? '#dc2626' :
                          guest.tw_status === 'Rental Returned' ? '#16a34a' :
                          guest.tw_status === 'Ready to Ride' ? '#2563eb' :
                          'var(--bg-deep)',
            }}>{guest.tw_status}</span>
          )}
        </div>
      </div>

      {/* T&C (Epic Waivers) */}
      <div className="status-cell">
        <WaiverFraction completed={guest.epic_waivers.completed} expected={guest.epic_waivers.expected} />
      </div>

      {/* MPWR Waivers (was Polaris) */}
      <div className="status-cell">
        <WaiverFraction completed={guest.polaris_waivers.completed} expected={guest.polaris_waivers.expected} />
      </div>

      {/* OHV — V2: fraction for rentals, N/A for tours */}
      <div className="status-cell">
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

      {/* PAY (was Deposit) */}
      <div className="status-cell">
        {guest.deposit_status?.toLowerCase() === 'due' ? (
          <a
            href={guest.tw_link || `https://epic4x4.tripworks.com/trip/${guest.tw_confirmation}/bookings`}
            target="_blank"
            rel="noopener noreferrer"
            title="Open TripWorks reservation to collect payment"
            onClick={(e) => e.stopPropagation()}
            style={{ textDecoration: 'none' }}
          >
            <DepositBadge status={guest.deposit_status} adventureAssure={guest.adventure_assure} />
          </a>
        ) : (
          <DepositBadge status={guest.deposit_status} adventureAssure={guest.adventure_assure} />
        )}
      </div>

      {/* AA (Adventure Assure) — V2 new column */}
      <div className="status-cell">
        {isRental ? (
          guest.adventure_assure?.toLowerCase().includes('upgrade') || guest.adventure_assure?.toLowerCase().includes('paid') || guest.adventure_assure?.toLowerCase().includes('premium') ? (
            <span className="badge badge-ready" style={{ fontSize: '0.65rem', background: 'var(--polaris-blue)', color: '#fff' }}>PREM</span>
          ) : (
            <span className="badge badge-blue" style={{ fontSize: '0.65rem', background: 'var(--bg-deep)', color: 'var(--text-muted)' }}>STND</span>
          )
        ) : (
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>N/A</span>
        )}
      </div>

      {/* DEP (Security Deposit Hold) — clickable link to MPWR reservation */}
      <div className="status-cell">
        {isRental ? (
          guest.adventure_assure?.toLowerCase().includes('premi') || guest.adventure_assure?.toLowerCase().includes('paid') ? (
            <span className="badge badge-neutral" style={{ padding: '0 4px' }}>N/A</span>
          ) : guest.mpwr_link ? (
            <a
              href={guest.mpwr_link}
              target="_blank"
              rel="noopener noreferrer"
              className="deposit-link"
              title="Open MPWR reservation to collect deposit"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="badge badge-alert" style={{ fontSize: '0.85rem', cursor: 'pointer' }}>$</span>
            </a>
          ) : (
            <a
              href={guest.tw_link || `https://epic4x4.tripworks.com/trip/${guest.tw_confirmation}/bookings`}
              target="_blank"
              rel="noopener noreferrer"
              className="deposit-link"
              title="Open TripWorks reservation"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="badge badge-alert" style={{ fontSize: '0.85rem', cursor: 'pointer' }}>$</span>
            </a>
          )
        ) : (
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>—</span>
        )}
      </div>
    </div>
  );
}

function ColumnHeader() {
  return (
    <div className="arrival-row" style={{ background: 'transparent', border: 'none', cursor: 'default', padding: '4px var(--space-md)' }}>
      <span />
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Time</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Guest / Vehicle</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>T&C</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>MPWR</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>OHV</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>PAY</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>AA</span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', textAlign: 'center' }}>DEP</span>
    </div>
  );
}

export default function StaffDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [flyoutOpen, setFlyoutOpen] = useState(false);
  const [activeFilter, setActiveFilter] = useState('all');
  const [sortBy, setSortBy] = useState('activity_time');

  const fetchData = useCallback(async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const res = await axios.get(`${baseUrl}/api/arrivals`);
      setData(res.data);
    } catch (err) {
      console.error('Failed to fetch arrivals:', err);
    }
    setLoading(false);
  }, []);

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
            setData(msg.arrivals);
            setLoading(false);
          }
        } catch (e) {
          console.error("Error parsing WS message", e);
        }
      };
      
      ws.onclose = () => {
        // Exponential backoff or simple reconnect
        reconnectTimer = setTimeout(connectWS, 3000);
      };
      
      ws.onerror = (e) => {
        console.error("WebSocket error", e);
        ws.close();
      };
    };

    connectWS();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  const handleRowClick = (guest) => {
    setSelectedGuest(guest);
    setFlyoutOpen(true);
  };

  const handleCloseDetail = () => {
    setFlyoutOpen(false);
    setTimeout(() => setSelectedGuest(null), 300);
  };

  const handleUpdate = () => {
    fetchData();
    handleCloseDetail();
  };

  // V2: Filter logic
  const filterGuests = (guests) => {
    if (!guests) return [];
    if (activeFilter === 'rental') return guests.filter(g => g.booking_type?.toLowerCase() === 'rental');
    if (activeFilter === 'tour') return guests.filter(g => g.booking_type?.toLowerCase() === 'tour');
    return guests;
  };

  // V2: Sort checked-in by return time
  const sortCheckedIn = (guests) => {
    if (!guests) return [];
    if (sortBy === 'return_time') {
      return [...guests].sort((a, b) => {
        const aTime = a.rental_return_time || '99:99';
        const bTime = b.rental_return_time || '99:99';
        return aTime.localeCompare(bTime);
      });
    }
    return guests;
  };

  // V2: Split checked-in into ON RIDE vs RETURNED
  const checkedInOnRide = sortCheckedIn(
    filterGuests(data?.checked_in)?.filter(g => g.rental_status !== 'Returned' && g.tw_status !== 'Rental Returned')
  );
  const checkedInReturned = filterGuests(data?.checked_in)?.filter(g => g.rental_status === 'Returned' || g.tw_status === 'Rental Returned');

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-muted)' }}>
        <RefreshCw size={24} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ marginLeft: 'var(--space-sm)' }}>Loading arrivals...</span>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-lg)' }}>
        <div>
          <h1 className="font-display" style={{ fontSize: '1.75rem', letterSpacing: '0.08em' }}>
            Arrival Readiness Board
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Real-Time Check-In Status • {data?.total_today || 0} reservations today
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
          {/* V2: Filter tabs */}
          <div className="tv-tabs">
            <button className={`tv-tab ${activeFilter === 'rental' ? 'active' : ''}`} onClick={() => setActiveFilter('rental')}>
              <Truck size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Rentals
            </button>
            <button className={`tv-tab ${activeFilter === 'tour' ? 'active' : ''}`} onClick={() => setActiveFilter('tour')}>
              <Mountain size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Tours
            </button>
            <button className={`tv-tab ${activeFilter === 'all' ? 'active' : ''}`} onClick={() => setActiveFilter('all')}>
              All
            </button>
          </div>

          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {data?.last_refresh}
          </span>
          <button className="btn btn-ghost" onClick={fetchData} title="Refresh now">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* V2: Sort control */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--space-sm)', gap: 'var(--space-sm)' }}>
        <button
          className="btn btn-ghost"
          onClick={() => setSortBy(sortBy === 'activity_time' ? 'return_time' : 'activity_time')}
          style={{ fontSize: '0.75rem', padding: '4px 10px' }}
        >
          <ArrowUpDown size={12} />
          Sort: {sortBy === 'activity_time' ? 'Activity Time' : 'Return Time'}
        </button>
      </div>

      {/* Two-Column Layout: NOW/NEXT + UPCOMING (stacks on small screens via CSS) */}
      <div className="staff-grid-2col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-xl)' }}>
        {/* NOW / NEXT — 0 to 30 minutes */}
        <div>
          <div className="section-header">
            <span className="dot" style={{ background: 'var(--epic-red)', boxShadow: '0 0 8px var(--epic-red)' }} />
            <span>NOW / NEXT</span>
            <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              0 – 30 min
            </span>
          </div>
          <ColumnHeader />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            {filterGuests(data?.now_next)?.length > 0 ? (
              filterGuests(data.now_next).map((guest, idx) => (
                <ArrivalRow key={guest.tw_confirmation} guest={guest} onClick={handleRowClick} index={idx} />
              ))
            ) : (
              <div style={{ padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)' }}>
                <Clock size={32} style={{ marginBottom: 'var(--space-sm)', opacity: 0.5 }} />
                <p>No arrivals in the next 30 minutes</p>
              </div>
            )}
          </div>
        </div>

        {/* UPCOMING — 30 to 90+ minutes */}
        <div>
          <div className="section-header">
            <span className="dot" />
            <span>UPCOMING</span>
            <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              Next {filterGuests(data?.upcoming)?.length || 0} reservations
            </span>
          </div>
          <ColumnHeader />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            {filterGuests(data?.upcoming)?.length > 0 ? (
              filterGuests(data.upcoming).map((guest, idx) => (
                <ArrivalRow key={guest.tw_confirmation} guest={guest} onClick={handleRowClick} index={idx} />
              ))
            ) : (
              <div style={{ padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)' }}>
                <Users size={32} style={{ marginBottom: 'var(--space-sm)', opacity: 0.5 }} />
                <p>No upcoming arrivals</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* V2: ON RIDE section (checked-in but not returned) */}
      {checkedInOnRide?.length > 0 && (
        <div style={{ marginTop: 'var(--space-2xl)' }}>
          <div className="section-header">
            <span className="dot" style={{ background: 'var(--polaris-blue)', boxShadow: '0 0 8px var(--polaris-blue)' }} />
            <span>ON RIDE / CHECKED IN</span>
            <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              {checkedInOnRide.length} active
            </span>
          </div>
          <ColumnHeader />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)', opacity: 0.7 }}>
            {checkedInOnRide.map((guest, idx) => (
              <ArrivalRow key={guest.tw_confirmation} guest={guest} onClick={handleRowClick} index={idx} />
            ))}
          </div>
        </div>
      )}

      {/* V2: RETURNED section */}
      {checkedInReturned?.length > 0 && (
        <div style={{ marginTop: 'var(--space-xl)' }}>
          <div className="section-header">
            <span className="dot" style={{ background: 'var(--status-ready)' }} />
            <span>RETURNED</span>
            <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-body)', color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 'normal', fontWeight: 400 }}>
              {checkedInReturned.length} complete
            </span>
          </div>
          <ColumnHeader />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)', opacity: 0.4 }}>
            {checkedInReturned.map((guest, idx) => (
              <ArrivalRow key={guest.tw_confirmation} guest={guest} onClick={handleRowClick} index={idx} />
            ))}
          </div>
        </div>
      )}

      {/* Legend footer */}
      <div style={{ marginTop: 'var(--space-2xl)', padding: 'var(--space-md)', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', display: 'flex', gap: 'var(--space-xl)', flexWrap: 'wrap', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        <span><StatusIcon status="ready" size="sm" /> Ready</span>
        <span><StatusIcon status="alert" size="sm" /> Needs Attention</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>T&C = Epic Terms</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>MPWR = MPWR/Polaris Waiver</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>OHV = OHV Permit</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>PAY = Payment Status</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>AA = Adventure Assure</span>
      </div>

      {/* Detail Flyout */}
      <DetailFlyout
        guest={selectedGuest}
        open={flyoutOpen}
        onClose={handleCloseDetail}
        onUpdate={handleUpdate}
      />
    </div>
  );
}
