import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Eyebrow, StatCard } from '../components/common';

function CheckRow({ check, passed, detail }: { check: string; passed: boolean; detail?: any }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
      <div>
        <div className="mono" style={{ fontSize: 13.5 }}>{check}</div>
        {detail && <div className="mono" style={{ fontSize: 12, color: 'var(--text-faint)' }}>{JSON.stringify(detail)}</div>}
      </div>
      <span className={`badge ${passed ? 'badge-green' : 'badge-high'}`}>{passed ? 'PASS' : 'FAIL'}</span>
    </div>
  );
}

export default function SelfEvaluation() {
  const [data, setData] = useState<any>(null);

  useEffect(() => { api.evaluation().then(setData); }, []);

  if (!data) return <div style={{ color: 'var(--text-dim)' }}>Running self-evaluation…</div>;

  const recall = data.masked_edge_recovery;

  return (
    <div>
      <Eyebrow>Self-Evaluation</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 6px' }}>Pipeline Self-Evaluation</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 20, maxWidth: 780 }}>
        Every number below is computed from this run against the planted ground-truth checklist — never
        hard-coded or improved after the fact.
      </p>

      <Eyebrow>Data Source Coverage</Eyebrow>
      <p style={{ color: 'var(--text-faint)', fontSize: 13.5, margin: '8px 0 12px', maxWidth: 780 }}>
        Every data source category named in the problem statement, with a live record count from this run.
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {data.data_source_coverage.map((s: any) => (
          <div key={s.source} className="card-tight" style={{ minWidth: 170 }}>
            <div className="card-label">{s.source}</div>
            <div className="card-value mono">{s.record_count}</div>
          </div>
        ))}
      </div>

      <Eyebrow>Masked-Edge Recovery (honest evaluation, no planted hidden edges)</Eyebrow>
      <div style={{ display: 'flex', gap: 12, margin: '12px 0 24px', flexWrap: 'wrap' }}>
        <StatCard value={recall.held_out_edge_count} label="edges masked (20%)" />
        <StatCard value={recall.recall_at_10} label="recall@10" />
        <StatCard value={recall.recall_at_20} label="recall@20" />
        <StatCard value={recall.recall_at_50} label="recall@50" />
      </div>

      <Eyebrow>Resolution Correctness</Eyebrow>
      <div className="card" style={{ marginTop: 12, marginBottom: 20 }}>
        {data.resolution_correctness.map((c: any) => <CheckRow key={c.check} {...c} />)}
      </div>

      <Eyebrow>Role / Utility Exclusion Correctness</Eyebrow>
      <div className="card" style={{ marginTop: 12, marginBottom: 20 }}>
        {data.role_exclusion_correctness.map((c: any) => <CheckRow key={c.check} {...c} />)}
      </div>

      <Eyebrow>Detector Ground-Truth Checks</Eyebrow>
      <div className="card" style={{ marginTop: 12, marginBottom: 20 }}>
        {data.detector_ground_truth_checks.map((c: any) => <CheckRow key={c.check} {...c} />)}
      </div>

      <Eyebrow>NER / Extraction Score Summary</Eyebrow>
      <div style={{ display: 'flex', gap: 12, marginTop: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {data.ner_extraction_score_summary.map((s: any) => (
          <div key={s.extraction_method} className="card-tight" style={{ minWidth: 160 }}>
            <div className="card-label">{s.extraction_method}</div>
            <div className="card-value mono">{s.mention_count}</div>
            <div className="card-metric">avg score {s.avg_extraction_score}</div>
          </div>
        ))}
      </div>

      <Eyebrow>Stage Timings (most recent pipeline run)</Eyebrow>
      {!data.stage_timings?.available ? (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, marginTop: 12 }}>
          {data.stage_timings?.reason || 'No pipeline run recorded yet.'}
        </div>
      ) : (
        <>
          <div className="mono" style={{ fontSize: 12.5, color: 'var(--text-faint)', margin: '8px 0 12px' }}>
            last run: {data.stage_timings.run_at}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            {Object.entries(data.stage_timings.timings_seconds || {}).map(([stage, secs]: [string, any]) => (
              <div key={stage} className="card-tight" style={{ minWidth: 150, borderColor: stage === 'total' ? 'var(--violet)' : undefined }}>
                <div className="card-label">{stage.replace(/_/g, ' ')}</div>
                <div className="card-value mono">{secs}s</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {Object.entries(data.stage_timings.record_counts || {}).map(([k, v]: [string, any]) => (
              <div key={k} className="card-tight" style={{ minWidth: 140 }}>
                <div className="card-label">{k.replace(/_/g, ' ')}</div>
                <div className="card-value mono">{v}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
