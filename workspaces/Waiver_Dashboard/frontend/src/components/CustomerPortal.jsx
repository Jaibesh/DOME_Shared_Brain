/**
 * CustomerPortal.jsx — Mobile-first Customer Waiver Portal
 * 
 * Accessed via unique link: /portal/{TW_CONFIRMATION}
 * 
 * Features:
 *   - Welcome message with guest name
 *   - Countdown timer to ride start & End-of-ride state
 *   - Dynamic Rules card
 *   - Native Map Links & full header details
 *   - Waiver completion status with animated progress bars
 *   - Full-screen modal QR codes + native Share links
 *   - OHV permit upload with camera capture (rentals only) + Utah Course Link
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ExternalLink, Shield, FileText, AlertCircle, CheckCircle, QrCode, MapPin, Clock, Calendar, X, Share } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import axios from 'axios';
import CountdownTimer from './CountdownTimer';
import { WaiverFraction } from './StatusIcon';
import StatusIcon from './StatusIcon';
import OHVUploader from './OHVUploader';

function ProgressBar({ completed, expected }) {
  const safeExpected = expected < completed ? completed : expected;
  const percent = safeExpected > 0 ? Math.min(100, Math.round((completed / safeExpected) * 100)) : 0;
  const isComplete = safeExpected > 0 && completed >= safeExpected;
  return (
    <div style={{ width: '100%', height: '6px', background: 'var(--bg-deep)', borderRadius: '3px', overflow: 'hidden', marginTop: 'var(--space-sm)' }}>
      <div style={{ 
        height: '100%', 
        width: `${percent}%`, 
        background: isComplete ? 'var(--status-ready)' : 'var(--polaris-blue)',
        transition: 'width 1s ease-out, background 0.3s',
        borderRadius: '3px'
      }} />
    </div>
  );
}

function QrModal({ isOpen, onClose, url, title }) {
  if (!isOpen) return null;
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.95)', zIndex: 9999, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-xl)' }}>
       <button onClick={onClose} style={{ position: 'absolute', top: '20px', right: '20px', background: 'transparent', border: 'none', color: '#fff', padding: '10px' }}><X size={36} /></button>
       <h2 style={{ color: '#fff', marginBottom: 'var(--space-xl)', textAlign: 'center', fontSize: '1.5rem' }}>{title}</h2>
       <div style={{ background: '#fff', padding: 'var(--space-xl)', borderRadius: 'var(--radius-lg)', boxShadow: '0 0 40px rgba(255,255,255,0.1)' }}>
         <QRCodeSVG value={url} size={280} level="M" />
       </div>
       <p style={{ color: 'var(--text-muted)', marginTop: 'var(--space-2xl)', textAlign: 'center', fontSize: '1.1rem' }}>Have your group scan this code with their phone camera.</p>
    </div>
  );
}

export default function CustomerPortal() {
  const { twConfirmation } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [epicQrModal, setEpicQrModal] = useState(false);
  const [polQrModal, setPolQrModal] = useState(false);
  const consecutiveFailures = { current: 0 };

  useEffect(() => {
    let isInitialFlow = true;

    const fetchPortal = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
        const res = await axios.get(`${baseUrl}/api/portal/${twConfirmation}`);
        setData(res.data);
        setError(''); // Clear error if recovered
        consecutiveFailures.current = 0;  // Reset backoff on success
      } catch (err) {
        if (isInitialFlow) {
          if (err.response?.status === 404) {
            setError('Reservation not found. Please check your confirmation code.');
          } else {
            setError('Unable to load your reservation. Please try again.');
          }
        } else {
          consecutiveFailures.current += 1;
          console.warn(`Background refresh failed (attempt ${consecutiveFailures.current}).`, err);
        }
      }
      setLoading(false);
      isInitialFlow = false;
    };
    fetchPortal();

    // Auto-refresh with exponential backoff on repeated failures
    // Normal: 15s, after 3+ failures: 30s, 60s max
    let intervalId = null;
    const scheduleNext = () => {
      const baseDelay = 15000;
      const delay = consecutiveFailures.current >= 3
        ? Math.min(baseDelay * Math.pow(2, consecutiveFailures.current - 2), 60000)
        : baseDelay;
      intervalId = setTimeout(async () => {
        await fetchPortal();
        scheduleNext();
      }, delay);
    };
    scheduleNext();
    return () => clearTimeout(intervalId);
  }, [twConfirmation]);

  if (loading) {
    return (
      <div className="portal-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
          <img src="/E4A_Stacked_Primary.png" alt="Epic 4x4 Adventures" style={{ width: '120px', marginBottom: 'var(--space-lg)' }} />
          <div style={{ fontSize: '2rem', marginBottom: 'var(--space-sm)', animation: 'pulse-calm 2s infinite' }}>🏔️</div>
          <p>Loading your adventure...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portal-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <img src="/E4A_Stacked_Primary.png" alt="Epic 4x4 Adventures" style={{ width: '140px', marginBottom: 'var(--space-xl)', display: 'block', marginLeft: 'auto', marginRight: 'auto' }} />
          <AlertCircle size={40} color="var(--epic-red)" style={{ marginBottom: 'var(--space-md)' }} />
          <h2 style={{ fontSize: '1.25rem', marginBottom: 'var(--space-sm)' }}>Oops!</h2>
          <p style={{ color: 'var(--text-secondary)' }}>{error}</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 'var(--space-md)' }}>
            Confirmation Code: <strong>{twConfirmation}</strong>
          </p>
        </div>
      </div>
    );
  }

  const firstName = data.guest_name.split(' ')[0];
  
  let formattedDate = data.activity_date;
  if (data.activity_date) {
    try {
      const parts = data.activity_date.split('-');
      if (parts.length === 3) {
        const [y, m, d] = parts;
        const dObj = new Date(y, m - 1, d);
        formattedDate = dObj.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
      }
    } catch(e) {}
  }
  
  const isRental = data.booking_type?.toLowerCase() === 'rental';
  const epicComplete = data.epic_waivers.completed >= data.epic_waivers.expected && data.epic_waivers.expected > 0;
  const polComplete = data.polaris_waivers.completed >= data.polaris_waivers.expected && data.polaris_waivers.expected > 0;
  const allDone = epicComplete && polComplete && (!data.ohv_required || data.ohv_uploaded);

  // Check if ride has ended
  let hasEnded = false;
  if (data.activity_date && data.rental_return_time) {
     const endDateTime = new Date(`${data.activity_date} ${data.rental_return_time}`);
     if (new Date() > endDateTime) {
        hasEnded = true;
     }
  }

  const epicWaiverTitle = isRental ? "Epic 4x4 Rental Agreement" : "Epic 4x4 Guide Services Agreement";
  const mapQuery = encodeURIComponent(isRental ? "11860 S Hwy 191, Moab, UT 84532" : "1041 S Main St, Moab, UT 84532");
  const mapLink = `https://www.google.com/maps/search/?api=1&query=${mapQuery}`;

  const handleNativeShare = async (url, title) => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: title,
          url: url
        });
      } catch (err) {
        console.log('User cancelled share or share failed', err);
      }
    } else {
      navigator.clipboard.writeText(url);
      alert('Link copied to clipboard!');
    }
  };

  return (
    <div className="portal-container animate-fade-in">
      <QrModal isOpen={epicQrModal} onClose={() => setEpicQrModal(false)} url={data.epic_waiver_url} title={epicWaiverTitle} />
      <QrModal isOpen={polQrModal} onClose={() => setPolQrModal(false)} url={data.polaris_waiver_url} title="Polaris Adventure Agreement" />

      {/* Logo & Welcome */}
      <div className="portal-header">
        <img src="/E4A_Stacked_Primary.png" alt="Epic 4x4 Adventures" style={{ width: '160px', height: 'auto' }} />
        <h1 className="portal-welcome">Welcome, {firstName}!</h1>
      </div>

      {/* Header Details */}
      <div style={{ background: 'rgba(255,255,255,0.05)', padding: 'var(--space-md)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-lg)', border: '1px solid rgba(255,255,255,0.1)' }}>
         <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-sm)' }}>
           <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>{isRental ? `${data.vehicle_model || data.activity_name} Rental` : data.activity_name}</span>
         </div>
         <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-xs)' }}>
           <Calendar size={16} color="var(--polaris-blue)" />
           <span style={{ fontSize: '0.85rem' }}>{formattedDate}</span>
         </div>
         <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-xs)' }}>
           <Clock size={16} color="var(--polaris-blue)" />
           <span style={{ fontSize: '0.85rem' }}>{data.activity_time} {data.rental_return_time ? `– ${data.rental_return_time}` : ''}</span>
         </div>
         <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
           <MapPin size={16} color="var(--polaris-blue)" />
           <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{isRental ? "Pick Up: " : "Tour Meets At: "}</span>
           <a href={mapLink} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.85rem', color: '#fff', textDecoration: 'underline', textUnderlineOffset: 3 }}>
             {isRental ? "11860 S Hwy 191, Moab, UT" : "1041 S Main St, Moab, UT"}
           </a>
         </div>
      </div>

      {/* End of Ride vs Countdown */}
      {hasEnded ? (
        <div style={{ background: 'var(--bg-deep)', border: '1px solid var(--polaris-blue)', borderRadius: 'var(--radius-md)', padding: 'var(--space-lg)', textAlign: 'center', marginBottom: 'var(--space-xl)' }}>
          <h2 style={{ fontSize: '1.25rem', color: '#fff', marginBottom: 'var(--space-xs)' }}>Adventure Complete</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Thank you for riding with Epic 4x4 Adventures!</p>
        </div>
      ) : (
        <CountdownTimer targetISO={data.countdown_target_iso} />
      )}

      {/* Rules Card */}
      {!allDone && (
        <div style={{ background: 'var(--bg-surface)', padding: 'var(--space-md)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-lg)', borderLeft: '4px solid var(--polaris-blue)' }}>
          <h3 style={{ fontSize: '0.9rem', marginBottom: 'var(--space-sm)', color: '#fff' }}>Requirements before your ride:</h3>
          <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: 'var(--space-md)', margin: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <li><strong>Everyone 18+</strong> must complete their own Polaris Adventure Agreement and upload a driver's license/ID.</li>
            <li><strong>Children</strong> can be added as participants under their parent's Polaris Agreement.</li>
            {isRental ? (
              <>
                <li><strong>Anyone driving</strong> must complete the Utah OHV Course and upload their certificate below.</li>
                <li><strong>Only ONE</strong> Epic 4x4 Rental Agreement is required per reservation (completed by the financially responsible party).</li>
              </>
            ) : (
              <li><strong>Every person</strong> going on the tour must fill out an Epic 4x4 Guide Services Agreement.</li>
            )}
          </ul>
        </div>
      )}

      {/* All Done Banner */}
      {allDone && (
        <div style={{ background: 'var(--status-ready-dim)', border: '1px solid var(--status-ready)', borderRadius: 'var(--radius-md)', padding: 'var(--space-md)', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-xl)' }}>
          <CheckCircle size={20} color="var(--status-ready)" />
          <span style={{ color: 'var(--status-ready)', fontWeight: 700 }}>You're all set! See you soon! 🎉</span>
        </div>
      )}

      {/* Section Divider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-lg)' }}>
        <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Waivers</span>
        <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
      </div>

      {/* Epic Waiver Card */}
      <div className="portal-waiver-card">
        <div className="waiver-header" style={{ marginBottom: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
            <Shield size={18} color="var(--epic-red)" />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span className="waiver-title">{epicWaiverTitle}</span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Estimated: 1-2 minutes</span>
            </div>
          </div>
          <WaiverFraction completed={data.epic_waivers.completed} expected={data.epic_waivers.expected} />
        </div>
        <ProgressBar completed={data.epic_waivers.completed} expected={data.epic_waivers.expected} />

        <div style={{ marginTop: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
          {data.epic_waivers.expected > 0 && (
            <>
              {data.epic_waivers.names.map((name, i) => (
                <div key={i} className="waiver-person"><StatusIcon status="ready" size="sm" /><span>{name}</span><span style={{ fontSize: '0.75rem', color: 'var(--status-ready)' }}>Done</span></div>
              ))}
              {Array.from({ length: Math.max(0, data.epic_waivers.completed - data.epic_waivers.names.length) }).map((_, i) => (
                <div key={`anon-epic-${i}`} className="waiver-person"><StatusIcon status="ready" size="sm" /><span style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>Signed Online</span><span style={{ fontSize: '0.75rem', color: 'var(--status-ready)' }}>Done</span></div>
              ))}
              {Array.from({ length: Math.max(0, data.epic_waivers.expected - Math.max(data.epic_waivers.completed, data.epic_waivers.names.length)) }).map((_, i) => (
                <div key={`open-epic-${i}`} className="waiver-person"><StatusIcon status="neutral" size="sm" /><span style={{ color: 'var(--text-muted)' }}>Awaiting signature</span></div>
              ))}
            </>
          )}
        </div>

        {!epicComplete && data.epic_waiver_url?.trim() && (
          <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
            <a href={data.epic_waiver_url} target="_blank" rel="noopener noreferrer" className="btn btn-danger btn-block" style={{ flex: 1, padding: '12px' }}>
              <ExternalLink size={16} /> Complete
            </a>
            <button className="btn btn-outline" onClick={() => setEpicQrModal(true)} style={{ padding: '12px 16px' }} title="Show QR Code">
              <QrCode size={18} />
            </button>
            <button className="btn btn-outline" onClick={() => handleNativeShare(data.epic_waiver_url, epicWaiverTitle)} style={{ padding: '12px 16px' }} title="Share Link">
              <Share size={18} />
            </button>
          </div>
        )}
      </div>

      {/* Polaris Waiver Card */}
      <div className="portal-waiver-card">
        <div className="waiver-header" style={{ marginBottom: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
            <FileText size={18} color="var(--polaris-blue)" />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span className="waiver-title">Polaris Adventure Agreement</span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Estimated: 8-10 minutes</span>
            </div>
          </div>
          <WaiverFraction completed={data.polaris_waivers.completed} expected={data.polaris_waivers.expected} />
        </div>
        <ProgressBar completed={data.polaris_waivers.completed} expected={data.polaris_waivers.expected} />

        <div style={{ marginTop: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
          {data.polaris_waivers.expected > 0 && (
            <>
              {data.polaris_waivers.names.map((name, i) => (
                <div key={i} className="waiver-person"><StatusIcon status="ready" size="sm" /><span>{name}</span><span style={{ fontSize: '0.75rem', color: 'var(--status-ready)' }}>Done</span></div>
              ))}
              {Array.from({ length: Math.max(0, data.polaris_waivers.completed - data.polaris_waivers.names.length) }).map((_, i) => (
                <div key={`anon-pol-${i}`} className="waiver-person"><StatusIcon status="ready" size="sm" /><span style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>Signed Online</span><span style={{ fontSize: '0.75rem', color: 'var(--status-ready)' }}>Done</span></div>
              ))}
              {Array.from({ length: Math.max(0, data.polaris_waivers.expected - Math.max(data.polaris_waivers.completed, data.polaris_waivers.names.length)) }).map((_, i) => (
                <div key={`open-pol-${i}`} className="waiver-person"><StatusIcon status="neutral" size="sm" /><span style={{ color: 'var(--text-muted)' }}>Awaiting signature</span></div>
              ))}
            </>
          )}
        </div>

        {!polComplete && data.polaris_waiver_url?.trim() && (
          <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
            <a href={data.polaris_waiver_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-block" style={{ flex: 1, padding: '12px' }}>
              <ExternalLink size={16} /> Complete
            </a>
            <button className="btn btn-outline" onClick={() => setPolQrModal(true)} style={{ padding: '12px 16px' }} title="Show QR Code">
              <QrCode size={18} />
            </button>
            <button className="btn btn-outline" onClick={() => handleNativeShare(data.polaris_waiver_url, "Polaris Adventure Agreement")} style={{ padding: '12px 16px' }} title="Share Link">
              <Share size={18} />
            </button>
          </div>
        )}
        {!polComplete && !data.polaris_waiver_url?.trim() && (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center' }}>Polaris waiver link will be available shortly.</p>
        )}
      </div>

      {/* OHV Upload (Rentals Only) */}
      {data.ohv_required && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-md)' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em' }}>OHV Permit</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
          </div>

          <a href="https://recreation.utah.gov/off-highway-vehicles/education/ohv-education-course/" target="_blank" rel="noopener noreferrer" className="btn btn-outline" style={{ display: 'flex', width: '100%', justifyContent: 'center', marginBottom: 'var(--space-md)', padding: '12px', borderColor: 'var(--polaris-blue)', color: 'var(--polaris-blue)' }}>
            <ExternalLink size={16} style={{ marginRight: 8 }} /> Take Utah OHV Course
          </a>

          <OHVUploader twConfirmation={twConfirmation} initialUploaded={data.ohv_uploaded} />
        </>
      )}

      {/* Footer */}
      <div style={{ textAlign: 'center', padding: 'var(--space-xl) 0', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
        <p>* Dashboard and portal status may take up to 60 seconds to reflect recent updates.</p>
        <p style={{ marginTop: 'var(--space-md)' }}>Confirmation: {twConfirmation}</p>
        <p style={{ marginTop: 'var(--space-xs)' }}>© {new Date().getFullYear()} Epic 4x4 Adventures • Moab, Utah</p>
      </div>
    </div>
  );
}
