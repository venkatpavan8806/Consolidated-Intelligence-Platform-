import { useOutletContext } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow, FlagshipBanner, ConnectorChain, SeverityBadge } from '../components/common';

export default function WomenSafety() {
  const { womenSafety } = useOutletContext<DashboardData>();

  return (
    <div>
      <FlagshipBanner>Flagship Capability — NCRB Women Safety Division</FlagshipBanner>
      <h1 style={{ fontSize: 26, margin: '14px 0 6px' }}>Trafficking Network Analysis</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 8, maxWidth: 780 }}>
        This is not a separate detection model. It re-labels and filters the same community-detection
        and broker-scoring machinery used for general financial "kingpin" analysis, applied to the
        person/phone network. The same mechanism that surfaces a financial intermediary surfaces a
        trafficking one.
      </p>
      <Eyebrow>Two independent methods, merged and provenance-tagged</Eyebrow>

      {womenSafety.chain_candidates.length > 0 && (
        <div style={{ marginTop: 20, marginBottom: 32 }}>
          <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 14, maxWidth: 780 }}>
            The recruiter → transporter → receiver-side chain is structurally the same shape as this
            platform's connector-card motif, so it is rendered literally as three connected cards below —
            a deliberate, content-driven design choice, not decoration.
          </div>
          {womenSafety.chain_candidates.map((c, i) => (
            <div key={i} style={{ marginBottom: 16 }}>
              <ConnectorChain
                nodes={[
                  { label: 'Recruiter', value: c.recruiter.label, metric: c.recruiter.entity_type },
                  { label: 'Transporter / Intermediary', value: c.transporter.label, metric: c.transporter.entity_type },
                  { label: 'Receiver-side', value: c.receiver_side.label, metric: c.receiver_side.entity_type },
                ]}
              />
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
        <div>
          <Eyebrow>Recruiter Candidates</Eyebrow>
          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '8px 0 12px' }}>
            Fan-out to ≥3 low-degree contacts within one community. Intentionally generic — will also
            match unrelated hub structures (e.g. a burner-rotation phone). Every candidate requires
            human verification for exactly this reason.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {womenSafety.recruiters.map(r => (
              <div key={r.entity_id} className="card-tight">
                <div className="card-value mono" style={{ fontSize: 14 }}>{r.label}</div>
                <div className="card-metric">{r.entity_type} · fans out to {r.fanout_count} low-degree contacts</div>
              </div>
            ))}
            {womenSafety.recruiters.length === 0 && <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>None found.</div>}
          </div>
        </div>

        <div>
          <Eyebrow>Transporter / Intermediary Candidates</Eyebrow>
          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '8px 0 12px' }}>
            COMMUNITY_BRIDGE (neighbours span ≥2 Louvain communities) and STRUCTURAL_BRIDGE_PATH
            (primary, more reliable for small chains) are run independently and merged.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {womenSafety.transporters.map(t => (
              <div key={t.entity_id} className="card-tight">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div className="card-value mono" style={{ fontSize: 14 }}>{t.label}</div>
                  <div>{t.methods.map(m => <span key={m} className="badge badge-violet" style={{ marginLeft: 4 }}>{m}</span>)}</div>
                </div>
                <div className="card-metric">{t.entity_type}</div>
              </div>
            ))}
            {womenSafety.transporters.length === 0 && <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>None found.</div>}
          </div>
        </div>
      </div>

      <Eyebrow>Repeat-Location Signal</Eyebrow>
      <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '8px 0 12px', maxWidth: 780 }}>
        The same real-world location named across ≥3 independently-sourced records, tied to different
        entities — distinct from a location that recurs for a mundane reason (e.g. a police station name
        appearing on every FIR it filed), which is never surfaced here.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
        {womenSafety.repeat_locations.map(loc => (
          <div key={loc.entity_id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="card-value mono" style={{ fontSize: 14 }}>{loc.location}</span>
              <SeverityBadge severity="MEDIUM" />
            </div>
            <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>
              named in {loc.independent_source_count} independent records: {loc.source_records.join(', ')}
            </div>
          </div>
        ))}
        {womenSafety.repeat_locations.length === 0 && <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>None found.</div>}
      </div>
    </div>
  );
}
