import { useEffect, useState } from 'react';
import { Link, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow, SeverityBadge, humanize, caseTypeLabel } from '../components/common';
import { api, type ModuleStatus } from '../api/client';

export default function Leads() {
  const { leads, reload } = useOutletContext<DashboardData>();
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const [filter, setFilter] = useState<string>(searchParams.get('type') || 'ALL');
  const [busy, setBusy] = useState<string | null>(null);
  const [modules, setModules] = useState<ModuleStatus[]>([]);

  useEffect(() => {
    if (!caseId) return;
    api.moduleStatus(caseId).then(m => setModules(m.modules)).catch(() => setModules([]));
  }, [caseId, leads]);

  const types = ['ALL', ...Array.from(new Set(leads.map(l => l.lead_type)))];
  const activeFilter = types.includes(filter) ? filter : 'ALL';
  const visible = activeFilter === 'ALL' ? leads : leads.filter(l => l.lead_type === activeFilter);
  const heldModules = modules.filter(m => m.held_back_leads > 0);
  const heldTotal = heldModules.reduce((n, m) => n + m.held_back_leads, 0);

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
      <h1 style={{ fontSize: 30, margin: '10px 0 6px' }}>Leads</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 15, marginBottom: 16 }}>
        Every lead is evidence-backed and requires human verification. Nothing here is an accusation.
      </p>

      {heldTotal > 0 && (
        <div className="card-tight" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>
            {heldTotal} more lead{heldTotal === 1 ? '' : 's'} held back until a case type is confirmed
          </div>
          <div style={{ fontSize: 15, color: 'var(--text-dim)', margin: '4px 0 10px' }}>
            Detector modules only switch on for a case type an investigator has confirmed. Waiting:{' '}
            {heldModules.map((m, i) => (
              <span key={m.case_type}>
                {i > 0 && '; '}
                <strong>{caseTypeLabel(m.case_type)}</strong>
                {' '}({m.status === 'SUGGESTED' ? 'suggested' : m.status === 'REJECTED' ? 'rejected' : 'not yet suggested'}
                , {m.held_back_leads} lead{m.held_back_leads === 1 ? '' : 's'})
              </span>
            ))}
            .
          </div>
          <Link to={`/dashboard/${caseId}/overview`} className="btn" style={{ textDecoration: 'none', display: 'inline-block' }}>
            Review case types on Overview
          </Link>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        {types.map(t => (
          <button
            key={t}
            className="btn"
            style={{ fontSize: 15, borderColor: activeFilter === t ? 'var(--violet)' : undefined }}
            onClick={() => setFilter(t)}
          >
            {t === 'ALL' ? 'All' : humanize(t)} {t !== 'ALL' && `(${leads.filter(l => l.lead_type === t).length})`}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {visible.map(lead => (
          <div key={lead.lead_id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div>
                <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-dim)' }}>{humanize(lead.lead_type)}</span>
                {lead.method_provenance && (
                  <span style={{ marginLeft: 8 }}>
                    {lead.method_provenance.map(m => <span key={m} className="badge badge-violet" style={{ marginRight: 4 }}>{m}</span>)}
                  </span>
                )}
              </div>
              <SeverityBadge severity={lead.severity} />
            </div>
            <div style={{ fontSize: 16, marginBottom: 10 }}>{lead.summary}</div>

            {lead.signals.length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                {lead.signals.map((s, i) => (
                  <span key={i} className="mono" style={{ fontSize: 14, color: 'var(--text-dim)', background: 'var(--soft)', padding: '4px 10px', borderRadius: 6 }}>
                    {s.signal}: {String(s.value)}
                  </span>
                ))}
              </div>
            )}

            {lead.source_record_ids.length > 0 && (
              <div className="mono" style={{ fontSize: 14, color: 'var(--text-faint)', marginBottom: 10 }}>
                sources: {lead.source_record_ids.join(', ')}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {(['USEFUL', 'ALREADY_KNOWN', 'WRONG_PERSON'] as const).map(v => (
                <button
                  key={v}
                  className="btn"
                  style={{
                    fontSize: 14,
                    borderColor: lead.disposition?.disposition === v ? 'var(--violet)' : undefined,
                    opacity: busy === lead.lead_id ? 0.5 : 1,
                  }}
                  disabled={busy === lead.lead_id}
                  onClick={() => disposition(lead.lead_id, v)}
                >
                  {humanize(v)}
                </button>
              ))}
              {lead.disposition && (
                <span style={{ fontSize: 15, color: 'var(--text-faint)' }}>
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
