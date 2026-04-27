import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const formData = new URLSearchParams();
      formData.append('username', username);
      formData.append('password', password);

      const res = await axios.post(`${baseUrl}/api/login`, formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });

      const token = res.data.access_token;
      localStorage.setItem('staff_token', token);
      
      // Navigate to staff board
      navigate('/staff');
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: 'var(--bg-deep)',
      padding: 'var(--space-md)'
    }}>
      <div style={{
        backgroundColor: 'var(--bg-surface)',
        padding: 'var(--space-2xl)',
        borderRadius: '16px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
        width: '100%',
        maxWidth: '400px',
        border: '1px solid var(--border-light)'
      }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-xl)' }}>
          <img src="/E4A_Stacked_White.svg" alt="Epic 4x4 Adventures" style={{ height: '60px', marginBottom: 'var(--space-lg)' }} />
          <h2 style={{ color: 'var(--polaris-blue)', fontFamily: 'var(--font-display)', letterSpacing: '0.1em' }}>STAFF PORTAL</h2>
        </div>

        {error && (
          <div style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: 'var(--epic-red)',
            padding: 'var(--space-md)',
            borderRadius: '8px',
            marginBottom: 'var(--space-md)',
            fontSize: '0.9rem',
            textAlign: 'center',
            border: '1px solid var(--epic-red)'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 'var(--space-xs)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                backgroundColor: 'var(--bg-deep)',
                border: '1px solid var(--border-default)',
                borderRadius: '8px',
                color: 'var(--text-primary)'
              }}
              required
            />
          </div>
          
          <div>
            <label style={{ display: 'block', marginBottom: 'var(--space-xs)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                backgroundColor: 'var(--bg-deep)',
                border: '1px solid var(--border-default)',
                borderRadius: '8px',
                color: 'var(--text-primary)'
              }}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 'var(--space-sm)',
              padding: '14px',
              backgroundColor: 'var(--polaris-blue)',
              color: 'var(--bg-deep)',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 700,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
              transition: 'all 0.2s'
            }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
