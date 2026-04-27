/**
 * App.jsx — Three-Surface Router + Kiosk Mode
 * 
 * Routes:
 *   /staff     → Staff Operations Dashboard (with sidebar)
 *   /          → Staff Dashboard (default)
 *   /tv        → TV Board (all, fullscreen)
 *   /tv/rentals → TV Board (rentals only)
 *   /tv/tours   → TV Board (tours only)
 *   /portal/:twConfirmation → Customer Portal (direct link)
 *   /kiosk     → Guest Kiosk Search (iPad, locked)
 *   /kiosk/portal/:twConfirmation → Customer Portal (from kiosk, with back button)
 */

import { BrowserRouter, Routes, Route, NavLink, Outlet, Navigate, useParams, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Tv, Users, RefreshCw, ArrowLeft, LogOut } from 'lucide-react';
import axios from 'axios';
import StaffDashboard from './components/StaffDashboard';
import TVDashboard from './components/TVDashboard';
import CustomerPortal from './components/CustomerPortal';
import GuestKiosk from './components/GuestKiosk';
import Login from './components/Login';

// Axios Request Interceptor — only attach auth token to staff-protected endpoints
const STAFF_ENDPOINTS = ['/api/check-in', '/api/collect-payment', '/api/notes', '/api/refresh', '/api/login'];
axios.interceptors.request.use((config) => {
  const url = config.url || '';
  const isStaffEndpoint = STAFF_ENDPOINTS.some(ep => url.includes(ep));
  if (isStaffEndpoint) {
    const token = localStorage.getItem('staff_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Axios Response Interceptor — auto-redirect on expired/invalid token
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/api/login')) {
      localStorage.removeItem('staff_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth Guard Component
function RequireAuth({ children }) {
  const token = localStorage.getItem('staff_token');
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function StaffLayout() {
  return (
    <div className="dashboard-layout">
      <aside className="dashboard-sidebar">
        {/* Official Logo */}
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <img
            src="/E4A_Stacked_Primary.png"
            alt="Epic 4x4 Adventures"
            style={{ width: '100%', maxWidth: '180px', height: 'auto' }}
          />
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 'var(--space-sm)' }}>
            Operations Dashboard
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
          <NavLink
            to="/staff"
            className={({ isActive }) => `btn btn-ghost ${isActive ? 'active' : ''}`}
            style={({ isActive }) => ({
              justifyContent: 'flex-start',
              background: isActive ? 'var(--polaris-blue-dim)' : 'transparent',
              borderColor: isActive ? 'var(--polaris-blue)' : 'var(--border-default)',
              color: isActive ? 'var(--polaris-blue)' : 'var(--text-secondary)',
            })}
          >
            <LayoutDashboard size={16} />
            Staff Board
          </NavLink>

          <a
            href="/tv"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost"
            style={{ justifyContent: 'flex-start' }}
          >
            <Tv size={16} />
            Launch TV Board
          </a>

          <a
            href="/tv/rentals"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost"
            style={{ justifyContent: 'flex-start', paddingLeft: 'var(--space-xl)', fontSize: '0.8rem' }}
          >
            Rentals TV
          </a>

          <a
            href="/tv/tours"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost"
            style={{ justifyContent: 'flex-start', paddingLeft: 'var(--space-xl)', fontSize: '0.8rem' }}
          >
            Tours TV
          </a>
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Logout */}
        <button
          onClick={() => {
            localStorage.removeItem('staff_token');
            window.location.href = '/login';
          }}
          className="btn btn-ghost"
          style={{ justifyContent: 'flex-start', color: 'var(--text-secondary)' }}
        >
          <LogOut size={16} />
          Sign Out
        </button>

        {/* Footer */}
        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-default)', paddingTop: 'var(--space-md)' }}>
          <p>Drive Epic. Be Epic.</p>
          <p style={{ marginTop: 'var(--space-xs)' }}>v3.0 • Moab, Utah</p>
        </div>
      </aside>
      <main className="dashboard-main">
        <Outlet />
      </main>
    </div>
  );
}

/**
 * KioskPortalWrapper — Wraps CustomerPortal with a sticky "Back to Search" bar
 * and prevents navigation outside the kiosk flow.
 */
function KioskPortalWrapper() {
  const navigate = useNavigate();
  
  return (
    <div>
      <div className="kiosk-back-bar">
        <button className="kiosk-back-btn" onClick={() => navigate('/kiosk')}>
          <ArrowLeft size={18} />
          Back to Search
        </button>
      </div>
      <CustomerPortal />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Login Route */}
        <Route path="/login" element={<Login />} />

        {/* Staff Dashboard — Protected route with sidebar layout */}
        <Route element={<RequireAuth><StaffLayout /></RequireAuth>}>
          <Route path="/" element={<Navigate to="/staff" replace />} />
          <Route path="/staff" element={<StaffDashboard />} />
        </Route>

        {/* TV Board — fullscreen, no chrome */}
        <Route path="/tv" element={<TVDashboard filter="all" />} />
        <Route path="/tv/rentals" element={<TVDashboard filter="rental" />} />
        <Route path="/tv/tours" element={<TVDashboard filter="tour" />} />

        {/* Customer Portal — direct link (from email/QR) */}
        <Route path="/portal/:twConfirmation" element={<CustomerPortal />} />

        {/* Kiosk Mode — locked guest self-service */}
        <Route path="/kiosk" element={<GuestKiosk />} />
        <Route path="/kiosk/portal/:twConfirmation" element={<KioskPortalWrapper />} />
      </Routes>
    </BrowserRouter>
  );
}
