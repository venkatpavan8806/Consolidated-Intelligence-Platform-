import { useOutletContext } from 'react-router-dom';
import type { DashboardData } from './Dashboard';
import { Eyebrow, StatCard, SeverityBadge } from '../components/common';

export default function Overview() {
  const { graph, leads, reviewQueue } = useOutletContext<DashboardData>();

  const byType: Record<string, number> = {};
  for (const n of graph.nodes) byType[n.entity_type] = (byType[n.entity_type] || 0) + 1;

  const highSeverity = leads.filter(l => l.severity === 'HIGH').length;

  return (
    <div>
      <Eyebrow>Case Overview</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 20px' }}>Investigation Snapshot</h1>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 28 }}>
        <StatCard value={graph.nodes.length} label="entities in view" />
        <StatCard value={graph.links.length} label="relationships" />
        <StatCard value={leads.length} label="active leads" />
        <StatCard value={highSeverity} label="high severity" />
        <StatCard value={reviewQueue.length} label="review clusters pending" />
      </div>

      <Eyebrow>Entity Mix</Eyebrow>
      <div className="connector-row" style={{ marginTop: 12, marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        {Object.entries(byType).map(([type, count]) => (
          <div key={type} className="card-tight" style={{ minWidth: 120 }}>
            <div className="card-label">{type}</div>
            <div className="card-value mono">{count}</div>
          </div>
        ))}
      </div>

      <Eyebrow>Recent High-Severity Leads</Eyebrow>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
        {leads.filter(l => l.severity === 'HIGH').slice(0, 6).map(l => (
          <div key={l.lead_id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)' }}>{l.lead_type}</span>
              <SeverityBadge severity={l.severity} />
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{l.summary}</div>
          </div>
        ))}
        {leads.filter(l => l.severity === 'HIGH').length === 0 && (
          <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>No high-severity leads in view.</div>
        )}
      </div>
    </div>
  );
}
