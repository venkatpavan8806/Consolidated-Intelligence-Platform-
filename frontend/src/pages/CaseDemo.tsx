import { useEffect, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow, caseTypeLabel, humanize } from '../components/common';
import { api, type EvidenceSource, type EvidenceSummary, type ModuleStatusResponse } from '../api/client';
import { CASE_STORIES, GENERIC_STORY, type StoryStep } from '../content/caseStories';

// A self-explaining walkthrough of one case: what happened, which Digital and
// Physical records are connected (live counts), what each detector module
// found (live lead counts, linked into the Leads tab), and what stays a human
// decision. The prose comes from content/caseStories.ts; every number comes
// from the API, so the page can never drift from the data.

type LeadState =
  | { kind: 'active'; count: number }
  | { kind: 'held'; count: number; caseType: string }
  | { kind: 'none' };

function leadState(leadType: string, status: ModuleStatusResponse | null): LeadState {
  if (!status) return { kind: 'none' };
  const cross = status.cross_cutting_lead_type_counts[leadType];
  if (cross) return { kind: 'active', count: cross };
  for (const m of status.modules) {
    const c = m.lead_type_counts[leadType];
    if (!c) continue;
    if (c.active > 0) return { kind: 'active', count: c.active };
    if (c.held_back > 0) return { kind: 'held', count: c.held_back, caseType: m.case_type };
  }
  return { kind: 'none' };
}

function LeadChip({ leadType, caseId, state }: { leadType: string; caseId: string; state: LeadState }) {
  const name = humanize(leadType);
  if (state.kind === 'active') {
    return (
      <Link to={`/dashboard/${caseId}/leads?type=${leadType}`} className="badge badge-green" style={{ textDecoration: 'none' }}>
        {name} · {state.count} lead{state.count === 1 ? '' : 's'} → view
      </Link>
    );
  }
  if (state.kind === 'held') {
    return (
      <span className="badge badge-medium">
        {name} · {state.count} held back until {caseTypeLabel(state.caseType)} is confirmed
      </span>
    );
  }
  return <span className="badge badge-low">{name} · none found</span>;
}

function Step({ n, step, caseId, status }: { n: number; step: StoryStep; caseId: string; status: ModuleStatusResponse | null }) {
  return (
    <div className="card" style={{ display: 'flex', gap: 16 }}>
      <div
        style={{
          width: 36, height: 36, borderRadius: '50%', background: 'var(--violet)', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, flexShrink: 0,
        }}
      >
        {n}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{step.title}</div>
        <div style={{ fontSize: 16, color: 'var(--text-dim)' }}>{step.body}</div>
        {step.leadTypes && step.leadTypes.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            {step.leadTypes.map(lt => (
              <LeadChip key={lt} leadType={lt} caseId={caseId} state={leadState(lt, status)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EvidenceColumn({
  title, subtitle, sources, roles,
}: { title: string; subtitle: string; sources: EvidenceSource[]; roles: Record<string, string> }) {
  const present = sources.filter(s => s.count > 0);
  return (
    <div className="card" style={{ flex: 1, minWidth: 280 }}>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{title}</div>
      <div style={{ fontSize: 15, color: 'var(--text-faint)', marginBottom: 12 }}>{subtitle}</div>
      {present.length === 0 && (
        <div style={{ fontSize: 16, color: 'var(--text-faint)' }}>None for this case.</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {present.map(s => (
          <div key={s.key} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div className="stat-number" style={{ fontSize: 28, minWidth: 44, textAlign: 'right' }}>{s.count}</div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{s.label}</div>
              <div style={{ fontSize: 15, color: 'var(--text-dim)' }}>{roles[s.key] || 'Connected into this case.'}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CaseDemo() {
  const { caseId } = useParams();
  const { leads } = useOutletContext<DashboardData>();
  const [evidence, setEvidence] = useState<EvidenceSummary | null>(null);
  const [status, setStatus] = useState<ModuleStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId) return;
    api.evidenceSummary(caseId).then(setEvidence).catch(() => setError('Could not load the evidence summary.'));
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    api.moduleStatus(caseId).then(setStatus).catch(() => setError('Could not load module status.'));
  }, [caseId, leads]);

  if (!caseId) return null;
  const story = CASE_STORIES[caseId] ?? GENERIC_STORY;
  const digital = evidence?.sources.filter(s => s.branch === 'DIGITAL') ?? [];
  const physical = evidence?.sources.filter(s => s.branch === 'PHYSICAL') ?? [];
  const absent = evidence?.sources.filter(s => s.count === 0) ?? [];

  const confirmedTypes = status?.modules.filter(m => m.status === 'CONFIRMED') ?? [];
  const tryModule = story.tryIt ? status?.modules.find(m => m.case_type === story.tryIt!.caseType) : undefined;

  // Generic fallback: no scripted steps, so list every module that has leads.
  const liveModules = status?.modules.filter(m => m.active_leads + m.held_back_leads > 0) ?? [];

  return (
    <div>
      <Eyebrow>Case Demo</Eyebrow>
      <h1 style={{ fontSize: 30, margin: '10px 0 10px' }}>What this case shows</h1>

      {confirmedTypes.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {confirmedTypes.map(m => (
            <span key={m.case_type} className="badge badge-green">✓ {caseTypeLabel(m.case_type)}</span>
          ))}
        </div>
      )}
      <p style={{ fontSize: 20, fontWeight: 600, margin: '0 0 28px', maxWidth: 820 }}>{story.headline}</p>
      {error && <div style={{ color: 'var(--red)', marginBottom: 16 }}>{error}</div>}

      <Eyebrow>1. What happened</Eyebrow>
      <p style={{ fontSize: 17, margin: '8px 0 32px', maxWidth: 820 }}>{story.situation}</p>

      <Eyebrow>2. What we are connecting</Eyebrow>
      <p style={{ fontSize: 16, color: 'var(--text-dim)', margin: '8px 0 14px', maxWidth: 820 }}>
        These are the records held for this case right now, with live counts. Digital records are read directly;
        for physical evidence the platform reads the <em>paperwork about</em> the object (seizure registers, lab and
        post-mortem reports), never the object itself.
      </p>
      {!evidence && !error && <div style={{ color: 'var(--text-faint)' }}>Loading evidence…</div>}
      {evidence && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
          <EvidenceColumn
            title="Digital evidence"
            subtitle="Records the platform reads directly"
            sources={digital}
            roles={story.connects}
          />
          <EvidenceColumn
            title="Physical evidence"
            subtitle="Records about physical items"
            sources={physical}
            roles={story.connects}
          />
        </div>
      )}
      {story.graphNote && (
        <div className="card-tight" style={{ fontSize: 16, marginBottom: 12 }}>{story.graphNote}</div>
      )}
      {evidence && absent.length > 0 && (
        <details style={{ fontSize: 15, color: 'var(--text-faint)', marginBottom: 32 }}>
          <summary style={{ cursor: 'pointer' }}>Record types not present in this case ({absent.length})</summary>
          <div style={{ marginTop: 6 }}>{absent.map(a => a.label).join(' · ')}</div>
        </details>
      )}
      {evidence && absent.length === 0 && <div style={{ marginBottom: 32 }} />}

      <Eyebrow>3. What the platform does</Eyebrow>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, margin: '12px 0 32px' }}>
        {story.steps.map((step, i) => (
          <Step key={step.title} n={i + 1} step={step} caseId={caseId} status={status} />
        ))}
        {story.steps.length === 0 && liveModules.length === 0 && (
          <div style={{ color: 'var(--text-faint)', fontSize: 16 }}>No detector module has fired for this case yet.</div>
        )}
        {story.steps.length === 0 && liveModules.map(m => (
          <div key={m.case_type} className="card">
            <div style={{ fontSize: 18, fontWeight: 700 }}>{caseTypeLabel(m.case_type)} module</div>
            <div style={{ fontSize: 16, color: 'var(--text-dim)', margin: '4px 0 10px' }}>
              Status: {m.status.toLowerCase().replace('_', ' ')}. {m.active_leads} active lead{m.active_leads === 1 ? '' : 's'}, {m.held_back_leads} held back.
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.keys(m.lead_type_counts).map(lt => (
                <LeadChip key={lt} leadType={lt} caseId={caseId} state={leadState(lt, status)} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <Eyebrow>4. Where a human decides</Eyebrow>
      <div className="card" style={{ margin: '12px 0 32px', fontSize: 17 }}>{story.humanDecision}</div>

      {story.tryIt && (
        <>
          <Eyebrow>Try it live</Eyebrow>
          <div className="card" style={{ margin: '12px 0 32px' }}>
            <div style={{ fontSize: 17, marginBottom: 12 }}>{story.tryIt.text}</div>
            {tryModule && (
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                Right now, {caseTypeLabel(tryModule.case_type)} is{' '}
                {tryModule.status === 'CONFIRMED'
                  ? 'confirmed: its module is on.'
                  : `${tryModule.status === 'NOT_SUGGESTED' ? 'not yet suggested' : tryModule.status.toLowerCase()}, with ${tryModule.held_back_leads} lead${tryModule.held_back_leads === 1 ? '' : 's'} held back.`}
              </div>
            )}
            <Link to={`/dashboard/${caseId}/overview`} className="btn btn-primary" style={{ textDecoration: 'none', display: 'inline-block' }}>
              Go to Overview to decide
            </Link>
          </div>
        </>
      )}

      <Eyebrow>Honest limits</Eyebrow>
      <ul style={{ fontSize: 16, color: 'var(--text-dim)', margin: '10px 0 32px', paddingLeft: 22, maxWidth: 820 }}>
        {story.limits.map(l => <li key={l} style={{ marginBottom: 6 }}>{l}</li>)}
      </ul>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Link to={`/dashboard/${caseId}/graph`} className="btn" style={{ textDecoration: 'none' }}>Open the graph</Link>
        <Link to={`/dashboard/${caseId}/leads`} className="btn" style={{ textDecoration: 'none' }}>Open all leads</Link>
        <Link to={`/dashboard/${caseId}/overview`} className="btn" style={{ textDecoration: 'none' }}>Open overview</Link>
      </div>
    </div>
  );
}
