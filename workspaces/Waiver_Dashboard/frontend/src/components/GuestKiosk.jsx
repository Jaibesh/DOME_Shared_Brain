/**
 * GuestKiosk.jsx — iPad Kiosk Search Screen
 * 
 * A branded, locked-down search interface for guest self-service.
 * Accepts TW Confirmation codes (AIRK-WWMB) or MPWR numbers (CO-GGQ-GKM).
 * Navigates to the customer portal on successful lookup.
 */

import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, AlertCircle } from 'lucide-react';
import axios from 'axios';

export default function GuestKiosk() {
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Auto-focus the search input
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Auto-clear error after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const q = query.trim().toUpperCase();
    if (!q) return;

    setLoading(true);
    setError('');

    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const res = await axios.get(`${baseUrl}/api/resolve-confirmation?q=${encodeURIComponent(q)}`);
      if (res.data?.tw_confirmation) {
        navigate(`/kiosk/portal/${res.data.tw_confirmation}`);
      } else {
        setError('Reservation not found. Please check your code and try again.');
      }
    } catch (err) {
      if (err.response?.status === 404) {
        setError('Reservation not found. Please check your confirmation code.');
      } else {
        setError('Something went wrong. Please try again or ask a staff member.');
      }
    }
    setLoading(false);
  };

  return (
    <div className="kiosk-container">
      <div className="kiosk-card animate-fade-in">
        {/* Logo */}
        <img
          src="/E4A_Stacked_Primary.png"
          alt="Epic 4x4 Adventures"
          style={{ width: '180px', height: 'auto', marginBottom: 'var(--space-xl)' }}
        />

        {/* Welcome text */}
        <h1 className="font-display" style={{ fontSize: '2rem', marginBottom: 'var(--space-sm)', letterSpacing: '0.08em' }}>
          Welcome!
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', marginBottom: 'var(--space-xl)', lineHeight: 1.5 }}>
          Enter your confirmation code to view your reservation and complete any required waivers.
        </p>

        {/* Search form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          <input
            ref={inputRef}
            type="text"
            className="kiosk-search-input"
            placeholder="e.g. AIRK-WWMB or CO-GGQ-GKM"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck="false"
          />

          <button
            type="submit"
            className="btn btn-primary btn-lg btn-block"
            disabled={loading || !query.trim()}
            style={{ opacity: loading || !query.trim() ? 0.5 : 1 }}
          >
            {loading ? (
              <span style={{ animation: 'pulse-calm 1s infinite' }}>Looking up...</span>
            ) : (
              <>
                <Search size={20} />
                Find My Reservation
              </>
            )}
          </button>
        </form>

        {/* Error message */}
        {error && (
          <div className="kiosk-error animate-fade-in">
            <AlertCircle size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            {error}
          </div>
        )}

        {/* Help text */}
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 'var(--space-xl)' }}>
          Your confirmation code was sent in your booking email.
          <br />Ask a staff member if you need help.
        </p>
      </div>

      {/* Footer */}
      <div style={{ textAlign: 'center', padding: 'var(--space-xl) 0', color: 'var(--text-muted)', fontSize: '0.7rem' }}>
        <p>&copy; {new Date().getFullYear()} Epic 4x4 Adventures &bull; Moab, Utah</p>
      </div>
    </div>
  );
}
