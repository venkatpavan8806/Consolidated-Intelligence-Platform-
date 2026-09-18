import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow, SeverityBadge } from '../components/common';
import { api } from '../api/client';

export default function Leads() {
  const { leads, reload } = useOutletContext<DashboardData>();
  const [filter, setFilter] = useState<string>('ALL');
  const [busy, setBusy] = useState<string | null>(null);

  const types = ['ALL', ...Array.from(new Set(leads.map(l => l.lead_type)))];
  const visible = filter === 'ALL' ? leads : leads.filter(l => l.lead_type === filter);

  async function disposition(leadId: string, value: string) {
    setBusy(leadId);
    try {
      await api.setDisposition(leadId, value);
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <Eyebrow>Investigative Leads</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 6px' }}>Leads</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 16 }}>
        Every lead is evidence-backed and requires human verification. Nothing here is an accusation.
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        {types.map(t => (
          <button
            key={t}
            className="btn"
            style={{ fontSize: 12.5, borderColor: filter === t ? 'var(--violet)' : undefined }}
            onClick={() => setFilter(t)}
          >
            {t} {t !== 'ALL' && `(${leads.filter(l => l.lead_type === t).length})`}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {visible.map(lead => (
          <div key={lead.lead_id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div>
                <span className="mono" style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{lead.lead_type}</span>
                {lead.method_provenance && (
                  <span style={{ marginLeft: 8 }}>
                    {lead.method_provenance.map(m => <span key={m} className="badge badge-violet" style={{ marginRight: 4 }}>{m}</span>)}
                  </span>
                )}
              </div>
              <SeverityBadge severity={lead.severity} />
            </div>
            <div style={{ fontSize: 13.5, marginBottom: 10 }}>{lead.summary}</div>

            {lead.signals.length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                {lead.signals.map((s, i) => (
                  <span key={i} className="mono" style={{ fontSize: 12, color: 'var(--text-dim)', background: 'var(--card)', padding: '3px 8px', borderRadius: 8, border: '1px solid var(--line)' }}>
                    {s.signal}: {String(s.value)}
                  </span>
                ))}
              </div>
            )}

            {lead.source_record_ids.length > 0 && (
              <div className="mono" style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 10 }}>
                sources: {lead.source_record_ids.join(', ')}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {(['USEFUL', 'ALREADY_KNOWN', 'WRONG_PERSON'] as const).map(v => (
                <button
                  key={v}
                  className="btn"
                  style={{
                    fontSize: 12,
                    borderColor: lead.disposition?.disposition === v ? 'var(--violet)' : undefined,
                    opacity: busy === lead.lead_id ? 0.5 : 1,
                  }}
                  disabled={busy === lead.lead_id}
                  onClick={() => disposition(lead.lead_id, v)}
                >
                  {v.replace('_', ' ')}
                </button>
              ))}
              {lead.disposition && (
                <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
                  marked {lead.disposition.disposition} by {lead.disposition.actor}
                </span>
              )}
            </div>
          </div>
        ))}
        {visible.length === 0 && <div style={{ color: 'var(--text-faint)' }}>No leads in this filter.</div>}
      </div>
    </div>
  );
}
