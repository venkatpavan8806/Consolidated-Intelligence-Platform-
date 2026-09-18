import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import ForceGraph2D from 'react-force-graph-2d';
import type { DashboardData } from './Dashboard';
import { Eyebrow, ENTITY_TYPE_COLORS } from '../components/common';
import { api } from '../api/client';

export default function GraphExplorer() {
  const { graph } = useOutletContext<DashboardData>();
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 560 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(entries => {
      const entry = entries[0];
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo(() => ({
    nodes: graph.nodes.map(n => ({ ...n })),
    links: graph.links.map(l => ({ ...l })),
  }), [graph]);

  function onNodeClick(node: any) {
    setSelected(node.id);
    api.entityDetail(node.id).then(setDetail).catch(() => setDetail(null));
  }

  return (
    <div>
      <Eyebrow>Graph Explorer</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 6px' }}>Relationship Graph</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 16 }}>
        Colour = entity type · red ring = excluded from ranking (official / utility) · dashed edge = NLP-extracted from FIR text
      </p>

      <div style={{ display: 'flex', gap: 16 }}>
        <div ref={containerRef} className="card" style={{ flex: 1, height: 560, padding: 0, overflow: 'hidden' }}>
          <ForceGraph2D
            ref={fgRef}
            width={size.width}
            height={size.height}
            graphData={graphData}
            backgroundColor="#020202"
            nodeLabel={(n: any) => `${n.label} (${n.entity_type})`}
            nodeRelSize={4}
            linkColor={(l: any) => (l.epistemic_status === 'NLP_EXTRACTED' ? 'rgba(156,140,245,0.5)' : 'rgba(95,192,130,0.5)')}
            linkLineDash={(l: any) => (l.epistemic_status === 'NLP_EXTRACTED' ? [3, 2] : null)}
            linkWidth={1}
            onNodeClick={onNodeClick}
            nodeCanvasObject={(node: any, ctx, globalScale) => {
              const r = 4.5;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fillStyle = ENTITY_TYPE_COLORS[node.entity_type] || '#a89fc4';
              ctx.fill();
              if (node.is_official || node.is_utility) {
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#e2685a';
                ctx.beginPath();
                ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
                ctx.stroke();
              }
              if (node.id === selected) {
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#ffffff';
                ctx.beginPath();
                ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
                ctx.stroke();
              }
              if (globalScale > 1.4) {
                ctx.font = '3px "JetBrains Mono"';
                ctx.fillStyle = 'rgba(255,255,255,0.7)';
                ctx.fillText(node.label, node.x + r + 2, node.y + 2);
              }
            }}
          />
        </div>

        <div className="card" style={{ width: 320, flexShrink: 0, height: 560, overflowY: 'auto' }}>
          <div className="card-label">Entity Detail</div>
          {!detail && <div style={{ color: 'var(--text-faint)', fontSize: 13, marginTop: 8 }}>Click a node to inspect its evidence.</div>}
          {detail && (
            <div style={{ marginTop: 10 }}>
              <div className="card-value mono" style={{ fontSize: 15 }}>{detail.entity.canonical_value}</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-faint)', marginTop: 2 }}>{detail.entity.entity_type}</div>
              {Boolean(detail.entity.is_official || detail.entity.is_utility) && (
                <div className="badge badge-high" style={{ marginTop: 8 }}>
                  EXCLUDED — {detail.entity.is_official ? 'OFFICIAL' : 'UTILITY'}
                </div>
              )}

              {detail.fir_records.length > 0 && (
                <>
                  <div className="card-label" style={{ marginTop: 16 }}>FIR Mentions ({detail.fir_records.length})</div>
                  {detail.fir_records.map((f: any) => (
                    <div key={f.fir_id} className="card-tight" style={{ marginTop: 6 }}>
                      <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{f.fir_id} · {f.station} · {f.date.slice(0, 10)}</div>
                      <div style={{ fontSize: 13.5, marginTop: 4 }}>{f.text}</div>
                    </div>
                  ))}
                </>
              )}

              {detail.intel_records && detail.intel_records.length > 0 && (
                <>
                  <div className="card-label" style={{ marginTop: 16 }}>Surveillance / Intelligence Reports ({detail.intel_records.length})</div>
                  {detail.intel_records.map((r: any) => (
                    <div key={r.record_id} className="card-tight" style={{ marginTop: 6 }}>
                      <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                        {r.record_id} · {r.source_category.replace(/_/g, ' ')} · {r.reporting_unit} · {r.date.slice(0, 10)}
                      </div>
                      <div style={{ fontSize: 13.5, marginTop: 4 }}>{r.text}</div>
                    </div>
                  ))}
                </>
              )}

              {detail.cdr_records.length > 0 && (
                <>
                  <div className="card-label" style={{ marginTop: 16 }}>Call Records ({detail.cdr_records.length})</div>
                  {detail.cdr_records.slice(0, 8).map((c: any) => (
                    <div key={c.record_id} className="mono" style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 4 }}>
                      {c.caller} → {c.callee} · {c.timestamp.slice(0, 16)} · {c.duration_sec}s
                    </div>
                  ))}
                </>
              )}

              {detail.transaction_records.length > 0 && (
                <>
                  <div className="card-label" style={{ marginTop: 16 }}>Transactions ({detail.transaction_records.length})</div>
                  {detail.transaction_records.slice(0, 8).map((t: any) => (
                    <div key={t.record_id} className="mono" style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 4 }}>
                      {t.sender} → {t.receiver} · ₹{t.amount.toLocaleString()} · {t.timestamp.slice(0, 10)}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
