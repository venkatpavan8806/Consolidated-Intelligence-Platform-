import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Eyebrow } from '../components/common';

export default function Login() {
  const [username, setUsername] = useState('investigator1');
  const [password, setPassword] = useState('investigator1pass');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate('/cases');
    } catch (err: any) {
      setError(err.message || 'login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="app-panel" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="orbit-ring left" />
        <div className="orbit-ring right" />
        <div className="orbit-ring inner left" />
        <form onSubmit={onSubmit} className="card" style={{ width: 380, position: 'relative', zIndex: 1 }}>
          <Eyebrow>Consolidated Intelligence Platform</Eyebrow>
          <h1 style={{ fontSize: 26, margin: '10px 0 4px' }}>Investigator Sign-In</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 24 }}>
            SIH26189 — AI-Powered Criminal Network Analysis System
          </p>

          <label style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>Username</label>
          <input className="input" style={{ margin: '6px 0 16px' }} value={username}
                 onChange={e => setUsername(e.target.value)} />

          <label style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>Password</label>
          <input className="input" style={{ margin: '6px 0 16px' }} type="password" value={password}
                 onChange={e => setPassword(e.target.value)} />

          {error && <div style={{ color: 'var(--red)', fontSize: 13, marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>

          <p style={{ fontSize: 12.5, color: 'var(--text-faint)', marginTop: 18 }}>
            Demo accounts: investigator1 / investigator2 (case-scoped) · admin1 (full access + audit tools)
          </p>
        </form>
      </div>
    </div>
  );
}
