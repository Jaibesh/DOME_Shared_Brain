/**
 * DetailFlyout.jsx — Slide-out detail panel (V2)
 * 
 * V2 Changes:
 *   - Waiver names grouped vertically under Epic / MPWR headers
 *   - Ages shown next to names (parsed from "Name (Age)" format)
 *   - Primary rider crown 👑
 *   - Renamed "Deposit" → "Payment Status"
 *   - QR codes for waiver links + customer portal
 *   - Customer Portal copy-link button
 *   - OHV permit uploader names
 *   - Rental return time with countdown
 *   - Minor flag ⚠️ indicator
 *   - Signed PDF link
 */

import { useState } from 'react';
import { X, ExternalLink, Check, DollarSign, FileUp, Copy, Truck, Crown, QrCode, Link2, Clock, AlertTriangle } from 'lucide-react';
import StatusIcon, { WaiverFraction, DepositBadge, AABadge } from './StatusIcon';
import axios from 'axios';
import { QRCodeCanvas } from 'qrcode.react';

function SimpleQR({ value, size = 120, label, onClick }) {
  return (
    <div style={{ textAlign: 'center', cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
      <div style={{ background: '#ffffff', padding: 6, borderRadius: 'var(--radius-sm)', display: 'inline-block' }}>
        <QRCodeCanvas value={value} size={size} bgColor="#ffffff" fgColor="#000000" level="M" />
      </div>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>{label}</div>
    </div>
  );
}

function QrModal({ isOpen, onClose, url, title }) {
  if (!isOpen) return null;
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.95)', zIndex: 9999, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-xl)' }} onClick={onClose}>
       <button onClick={onClose} style={{ position: 'absolute', top: '20px', right: '20px', background: 'transparent', border: 'none', color: '#fff', padding: '10px', cursor: 'pointer' }}><X size={36} /></button>
       <h2 style={{ color: '#fff', marginBottom: 'var(--space-xl)', textAlign: 'center', fontSize: '1.5rem' }}>{title}</h2>
       <div style={{ background: '#fff', padding: 'var(--space-xl)', borderRadius: 'var(--radius-lg)', boxShadow: '0 0 40px rgba(255,255,255,0.1)' }} onClick={e => e.stopPropagation()}>
         <QRCodeCanvas value={url} size={280} level="M" />
       </div>
    </div>
  );
}

function WaiverNameRow({ nameStr, primaryRider }) {
  // Parse "Justus Robison (25)" or "Minor Child (14 ⚠️MINOR)" format
  const match = nameStr.match(/^(.+?)\s*(?:\((\d+)(.*?)\))?$/);
  const name = match ? match[1].trim() : nameStr;
  const age = match ? match[2] : null;
  const isMinor = nameStr.includes('⚠️MINOR');
  const isPrimary = primaryRider && name.toLowerCase() === primaryRider.toLowerCase();

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', padding: '4px 0', fontSize: '0.85rem' }}>
      <StatusIcon status="ready" size="sm" />
      {isPrimary && <span title="Primary Rider / Driver" style={{ fontSize: '0.9rem' }}>👑</span>}
      <span style={{ color: 'var(--text-primary)', fontWeight: isPrimary ? 700 : 400 }}>{name}</span>
      {age && (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 400 }}>
          age {age}
        </span>
      )}
      {isMinor && (
        <span style={{ fontSize: '0.65rem', color: 'var(--epic-red)', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          <AlertTriangle size={10} /> MINOR
        </span>
      )}
      <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--status-ready)' }}>✓ Signed</span>
    </div>
  );
}

export default function DetailFlyout({ guest, open, onClose, onUpdate }) {
  const [notes, setNotes] = useState(guest?.notes || '');
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [portalCopied, setPortalCopied] = useState(false);
  const [qrExpanded, setQrExpanded] = useState(false);
  const [activeQrUrl, setActiveQrUrl] = useState(null);
  const [activeQrLabel, setActiveQrLabel] = useState('');

  if (!guest) return null;

  const isRental = guest.booking_type?.toLowerCase() === 'rental';

  const handleCheckIn = async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      await axios.post(`${baseUrl}/api/check-in/${guest.tw_confirmation}`, { staff_name: 'Staff' });
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Check-in failed:', err);
    }
  };

  const handleCollectPayment = async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      await axios.post(`${baseUrl}/api/collect-payment/${guest.tw_confirmation}`, { staff_name: 'Staff', notes: '' });
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Payment collection failed:', err);
    }
  };

  const handleSaveNotes = async () => {
    setSaving(true);
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      await axios.patch(`${baseUrl}/api/notes/${guest.tw_confirmation}`, { notes });
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Notes save failed:', err);
    }
    setSaving(false);
  };

  const copyMPWR = () => {
    navigator.clipboard.writeText(guest.mpwr_number);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyPortalLink = () => {
    const link = guest.customer_portal_link || `https://www.epicreservation.com/portal/${guest.tw_confirmation}`;
    navigator.clipboard.writeText(link);
    setPortalCopied(true);
    setTimeout(() => setPortalCopied(false), 2000);
  };

  const epicWaiverUrl = `https://epic4x4.tripworks.com/trip/${guest.tw_confirmation}/bookings`;
  const polarisWaiverUrl = guest.mpwr_waiver_link || (guest.mpwr_number ? 'https://adventures.polaris.com/our-outfitters/epic-4x4-adventures-O-DZ6-478/waiver/rider-info' : '');
  const portalUrl = guest.customer_portal_link || `https://www.epicreservation.com/portal/${guest.tw_confirmation}`;

  return (
    <>
      <QrModal isOpen={!!activeQrUrl} onClose={() => setActiveQrUrl(null)} url={activeQrUrl} title={activeQrLabel} />
      <div className={`flyout-overlay ${open ? 'open' : ''}`} onClick={onClose} />
      <div className={`flyout-panel ${open ? 'open' : ''}`}>
        {/* Header — V2: larger with vehicle + activity */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-lg)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{guest.guest_name}</h2>
              {guest.primary_rider === guest.guest_name && <span title="Primary Rider">👑</span>}
            </div>
            <p style={{ color: 'var(--polaris-blue)', fontSize: '0.95rem', fontWeight: 600 }}>
              {isRental ? (guest.vehicle_model || guest.activity_name) : (guest.activity_name || guest.vehicle_model)}
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-sm)', marginTop: 'var(--space-xs)', alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                {guest.activity_time} • {guest.booking_type} • {guest.party_size}p
              </span>
              {isRental && guest.rental_return_time && (
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Clock size={12} /> Returns {guest.rental_return_time}
                </span>
              )}
              {guest.adventure_assure !== 'None' && <AABadge type={guest.adventure_assure} />}
              {guest.trip_safe === 'Purchased' && (
                <span style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.3)', padding: '2px 8px', borderRadius: 6, fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.02em' }}>
                  🛡️ TripSafe
                </span>
              )}
            </div>
            {/* Quick action buttons for staff to jump into specific orders */}
            <div style={{ display: 'flex', gap: 'var(--space-sm)', marginTop: 'var(--space-md)', flexWrap: 'wrap' }}>
              <a href={guest.tw_link || `https://epic4x4.tripworks.com/trip/${guest.tw_confirmation}/bookings`} target="_blank" rel="noopener noreferrer" className="btn btn-ghost" style={{ padding: '6px 12px', fontSize: '0.8rem', height: 'auto', background: 'var(--bg-deep)' }}>
                <ExternalLink size={14} style={{ marginRight: 6 }} /> TripWorks Order
              </a>
              {guest.mpwr_link && (
                <a href={guest.mpwr_link} target="_blank" rel="noopener noreferrer" className="btn" style={{ padding: '6px 12px', fontSize: '0.8rem', height: 'auto', background: 'var(--polaris-blue)', color: '#fff', border: 'none' }}>
                  <ExternalLink size={14} style={{ marginRight: 6 }} /> MPWR Order
                </a>
              )}
            </div>
          </div>
          <button onClick={onClose} style={{ color: 'var(--text-muted)', padding: '4px' }}>
            <X size={20} />
          </button>
        </div>

        {/* Overall Status */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-sm)',
          padding: 'var(--space-md)', background: 'var(--bg-deep)',
          borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-lg)',
        }}>
          <StatusIcon status={guest.checked_in || ['Checked In', 'Rental Out'].includes(guest.tw_status) ? 'ready' : guest.overall_status === 'ready' ? 'ready' : 'alert'} />
          <span style={{ fontWeight: 700 }}>
            {guest.tw_status === 'Rental Out' ? `ON RIDE — Rental Out at ${guest.checked_in_at || ''}` :
             guest.tw_status === 'Checked In' ? `CHECKED IN at ${guest.checked_in_at || ''}` :
             guest.tw_status === 'No Show' ? 'NO SHOW' :
             guest.tw_status === 'Rental Returned' ? 'RETURNED' :
             guest.checked_in ? `Checked In at ${guest.checked_in_at}` :
             guest.overall_status === 'ready' ? 'READY FOR CHECK-IN' : 'NOT READY — Action Required'}
          </span>
          {guest.tw_status && guest.tw_status !== 'Not Checked In' && (
            <span style={{
              fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px', borderRadius: 4,
              color: '#fff', marginLeft: 'auto',
              background: guest.tw_status === 'Checked In' ? '#16a34a' :
                          guest.tw_status === 'Rental Out' ? '#ea580c' :
                          guest.tw_status === 'No Show' ? '#dc2626' :
                          guest.tw_status === 'Rental Returned' ? '#16a34a' :
                          guest.tw_status === 'Ready to Ride' ? '#2563eb' :
                          guest.tw_status === 'MPWR Waiver Required' ? '#ca8a04' :
                          'var(--bg-deep)',
            }}>{guest.tw_status}</span>
          )}
          {guest.rental_status && !guest.tw_status && (
            <span
              className={`badge ${
                guest.rental_status === 'Returned' ? 'badge-ready' :
                guest.rental_status === 'OVERDUE' ? 'badge-alert' :
                'badge-blue'
              }`}
              style={{
                marginLeft: 'auto',
                ...(guest.rental_status === 'OVERDUE' ? { animation: 'pulse-alert 1.5s ease-in-out infinite' } : {}),
              }}
            >
              {guest.rental_status === 'OVERDUE' ? '⚠ OVERDUE' : guest.rental_status}
            </span>
          )}
        </div>

        {/* V2: Waivers — grouped vertically by type with names */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Waivers
          </h3>

          {/* Epic Waivers */}
          <div style={{ padding: 'var(--space-sm)', background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-sm)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-xs)' }}>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Epic 4x4 Waiver</span>
              <WaiverFraction completed={guest.epic_waivers.completed} expected={guest.epic_waivers.expected} />
            </div>
            {guest.epic_waivers.names.length > 0 ? (
              guest.epic_waivers.names.map((name, i) => (
                <WaiverNameRow key={`epic-${i}`} nameStr={name} primaryRider={guest.primary_rider} />
              ))
            ) : guest.epic_waivers.completed > 0 ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic', padding: '4px 0' }}>
                {guest.epic_waivers.completed} signed (names pending sync)
              </div>
            ) : null}
            {guest.epic_waivers.completed < guest.epic_waivers.expected && (
              <div style={{ fontSize: '0.75rem', color: 'var(--status-alert)', marginTop: 4 }}>
                {guest.epic_waivers.expected - guest.epic_waivers.completed} still awaiting signature
              </div>
            )}
          </div>

          {/* MPWR / Polaris Waivers */}
          <div style={{ padding: 'var(--space-sm)', background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-sm)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-xs)' }}>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>MPWR Waiver</span>
              <WaiverFraction completed={guest.polaris_waivers.completed} expected={guest.polaris_waivers.expected} />
            </div>
            {guest.polaris_waivers.names.length > 0 ? (
              guest.polaris_waivers.names.map((name, i) => (
                <WaiverNameRow key={`pol-${i}`} nameStr={name} primaryRider={guest.primary_rider} />
              ))
            ) : guest.polaris_waivers.completed > 0 ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic', padding: '4px 0' }}>
                {guest.polaris_waivers.completed} signed (names pending sync)
              </div>
            ) : null}
            {guest.polaris_waivers.completed < guest.polaris_waivers.expected && (
              <div style={{ fontSize: '0.75rem', color: 'var(--status-alert)', marginTop: 4 }}>
                {guest.polaris_waivers.expected - guest.polaris_waivers.completed} still awaiting signature
              </div>
            )}
          </div>

          {/* V2: OHV Permit Names (rentals only) */}
          {isRental && (
            <div style={{ padding: 'var(--space-sm)', background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-xs)' }}>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>OHV Permits</span>
                {guest.ohv_expected > 0 ? (
                  <WaiverFraction completed={guest.ohv_complete} expected={guest.ohv_expected} />
                ) : (
                  <StatusIcon status={guest.ohv_uploaded ? 'ready' : 'alert'} size="sm" />
                )}
              </div>
              {guest.ohv_permit_names?.length > 0 ? (
                guest.ohv_permit_names.map((name, i) => (
                  <div key={`ohv-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', padding: '4px 0', fontSize: '0.85rem' }}>
                    <StatusIcon status="ready" size="sm" />
                    <span>{name}</span>
                    <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--status-ready)' }}>✓ Uploaded</span>
                  </div>
                ))
              ) : guest.ohv_uploaded ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--status-ready)', padding: '4px 0' }}>✓ Permit uploaded</div>
              ) : (
                <div style={{ fontSize: '0.75rem', color: 'var(--status-alert)', padding: '4px 0' }}>No OHV permit uploaded yet</div>
              )}
            </div>
          )}
        </div>

        {/* Payment Status (was Deposit) */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Payment Status
          </h3>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--space-sm) 0' }}>
            <span>TripWorks Balance</span>
            <DepositBadge status={guest.deposit_status} adventureAssure={guest.adventure_assure} />
          </div>
          {guest.amount_due > 0 && (
            <div style={{ fontSize: '0.8rem', color: 'var(--status-alert)', fontWeight: 600 }}>
              Amount Due: ${(guest.amount_due).toFixed(2)}
            </div>
          )}
          {isRental && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--space-sm) 0', borderTop: '1px solid var(--border-subtle)', marginTop: 'var(--space-xs)' }}>
              <span>Adventure Assure</span>
              <AABadge type={guest.adventure_assure} />
            </div>
          )}
        </div>

        {/* Confirmation Numbers */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Confirmation Numbers
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>TripWorks</span>
              <code style={{ background: 'var(--bg-deep)', padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}>
                {guest.tw_confirmation}
              </code>
            </div>
            
            {guest.mpwr_number && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>MPWR</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
                  <code style={{ background: 'var(--bg-deep)', padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', color: 'var(--polaris-blue)' }}>
                    {guest.mpwr_number}
                  </code>
                  <button onClick={copyMPWR} className="btn btn-ghost" style={{ padding: '2px 4px', height: 'auto', minHeight: 0 }}>
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Quick Links */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Quick Links
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            {/* V2: Copy Customer Portal link */}
            <button className="btn btn-ghost" onClick={copyPortalLink} style={{ justifyContent: 'flex-start' }}>
              {portalCopied ? <Check size={16} /> : <Link2 size={16} />}
              {portalCopied ? 'Link Copied!' : 'Copy Customer Portal Link'}
            </button>
          </div>
        </div>

        {/* V2: Waiver QR Codes (Collapsible) */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <div 
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', marginBottom: 'var(--space-xs)' }}
            onClick={() => setQrExpanded(!qrExpanded)}
          >
            <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
              Scan to Fill Waivers
            </h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--polaris-blue)' }}>
              {qrExpanded ? 'Hide QR Codes' : 'Show QR Codes'}
            </span>
          </div>
          
          <div className={`qr-section ${qrExpanded ? 'expanded' : ''}`} style={{ overflow: 'hidden', transition: 'max-height 0.3s ease-out', maxHeight: qrExpanded ? '500px' : '0' }}>
            <div style={{ display: 'flex', gap: 'var(--space-md)', flexWrap: 'wrap', justifyContent: 'center', paddingTop: 'var(--space-sm)' }}>
              <SimpleQR value={epicWaiverUrl} label="Epic Waiver" size={100} onClick={() => { setActiveQrUrl(epicWaiverUrl); setActiveQrLabel("Epic Waiver"); }} />
              {polarisWaiverUrl && <SimpleQR value={polarisWaiverUrl} label="MPWR Waiver" size={100} onClick={() => { setActiveQrUrl(polarisWaiverUrl); setActiveQrLabel("MPWR Waiver"); }} />}
              <SimpleQR value={portalUrl} label="Customer Portal" size={100} onClick={() => { setActiveQrUrl(portalUrl); setActiveQrLabel("Customer Portal"); }} />
            </div>
          </div>
        </div>

        {/* Notes */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Notes
          </h3>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add notes about this reservation..."
            rows={3}
            style={{
              width: '100%', background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)',
              padding: 'var(--space-sm)', fontFamily: 'var(--font-body)', fontSize: '0.85rem',
              resize: 'vertical',
            }}
          />
          <button
            className="btn btn-ghost"
            onClick={handleSaveNotes}
            disabled={saving}
            style={{ marginTop: 'var(--space-xs)', fontSize: '0.8rem' }}
          >
            {saving ? 'Saving...' : 'Save Notes'}
          </button>
        </div>

        {/* Action Buttons */}
        {!guest.checked_in && !['Checked In', 'Rental Out', 'No Show', 'Rental Returned'].includes(guest.tw_status) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)', borderTop: '1px solid var(--border-default)', paddingTop: 'var(--space-lg)' }}>
            {guest.overall_status === 'ready' && (
              <a
                href={guest.tw_link || `https://epic4x4.tripworks.com/trip/${guest.tw_confirmation}/bookings`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-success btn-block btn-lg"
                style={{ textDecoration: 'none', textAlign: 'center' }}
              >
                <ExternalLink size={20} /> Check In via TripWorks
              </a>
            )}
            {guest.deposit_status === 'Due' && (
              <button className="btn btn-primary btn-block" onClick={handleCollectPayment}>
                <DollarSign size={16} /> Collect Payment
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
