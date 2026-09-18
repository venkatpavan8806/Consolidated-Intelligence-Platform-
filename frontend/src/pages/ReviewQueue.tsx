import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow } from '../components/common';
import { api } from '../api/client';

export default function ReviewQueue() {
  const { reviewQueue, reload } = useOutletContext<DashboardData>();
  const [busy, setBusy] = useState<string | null>(null);

  async function resolve(clusterId: string, decision: string) {
    setBusy(clusterId);
    try {
      await api.resolveReview(clusterId, decision);
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <Eyebrow>Identity Resolution</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 6px' }}>Review Queue</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 16 }}>
        Name-similar mentions that could not be confirmed into one identity via a shared hard identifier.
        The system never merges on name similarity alone — these clusters await your judgement.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {reviewQueue.map(cluster => (
          <div key={cluster.cluster_id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="mono" style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{cluster.cluster_id} · {cluster.entity_type}</span>
              <span className="badge badge-medium">{cluster.status}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 10 }}>{cluster.reason}</div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {cluster.mentions.map(m => (
                <span key={m.mention_id} className="mono" style={{ fontSize: 12.5, background: 'var(--card)', padding: '4px 9px', borderRadius: 8, border: '1px solid var(--line)' }}>
                  {m.text}{m.fir_role ? ` (${m.fir_role})` : ''} · {m.source_record_id}
                </span>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              {(['MERGE', 'KEEP_SEPARATE', 'ESCALATE'] as const).map(d => (
                <button
                  key={d}
                  className="btn"
                  style={{ fontSize: 12 }}
                  disabled={busy === cluster.cluster_id || cluster.status !== 'PENDING'}
                  onClick={() => resolve(cluster.cluster_id, d)}
                >
                  {d.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        ))}
        {reviewQueue.length === 0 && <div style={{ color: 'var(--text-faint)' }}>No pending review clusters.</div>}
      </div>
    </div>
  );
}
