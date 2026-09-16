import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type CaseRow } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useCase } from '../context/CaseContext';
import { Eyebrow } from '../components/common';

export default function CaseSelect() {
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { user, logout } = useAuth();
  const { setActiveCase } = useCase();
  const navigate = useNavigate();

  useEffect(() => {
    api.listCases().then(setCases).catch(e => setError(e.message));
  }, []);

  function enter() {
    const c = cases.find(c => c.case_id === selected);
    if (!c) {
      setError('select a case');
      return;
    }
    if (reason.trim().length < 3) {
      setError('a reason for this query is required (minimum 3 characters) and is logged to the audit chain');
      return;
    }
    setActiveCase(c, reason.trim());
    navigate(`/dashboard/${c.case_id}/overview`);
  }

  return (
    <div className="app-shell">
      <div className="app-panel">
        <div className="orbit-ring left" />
        <div className="orbit-ring right" />
        <div style={{ position: 'relative', zIndex: 1, padding: '40px 48px', maxWidth: 720, margin: '0 auto', width: '100%' }}>
          <Eyebrow>Case Selection</Eyebrow>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <h1 style={{ fontSize: 28, margin: '10px 0 6px' }}>Select a Case</h1>
            <button className="btn" onClick={logout}>Sign out ({user?.username})</button>
          </div>
          <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 28 }}>
            Every case query is logged to the tamper-evident audit chain. A reason for this query is mandatory.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
            {cases.map(c => (
              <div
                key={c.case_id}
                className="card"
                onClick={() => setSelected(c.case_id)}
                style={{
                  cursor: 'pointer',
                  borderColor: selected === c.case_id ? 'var(--violet)' : 'var(--line)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{c.title}</div>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 4 }}>
                      {c.case_id} · {c.category} · opened {c.opened_date.slice(0, 10)}
                    </div>
                  </div>
                  {selected === c.case_id && <span className="badge badge-violet">SELECTED</span>}
                </div>
              </div>
            ))}
            {cases.length === 0 && <div style={{ color: 'var(--text-faint)' }}>No cases assigned to this account.</div>}
          </div>

          <label style={{ fontSize: 12, color: 'var(--text-dim)' }}>Reason for query (required, audit-logged)</label>
          <input
            className="input"
            style={{ margin: '6px 0 16px' }}
            placeholder="e.g. reviewing new leads following informant tip"
            value={reason}
            onChange={e => setReason(e.target.value)}
          />

          {error && <div style={{ color: 'var(--red)', fontSize: 13, marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" onClick={enter}>Enter Case Workspace</button>
        </div>
      </div>
    </div>
  );
}
