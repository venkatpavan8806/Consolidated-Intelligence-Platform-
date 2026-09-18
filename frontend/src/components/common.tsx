import type { ReactNode } from 'react';

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="eyebrow">
      <span className="bracket">{'}'}</span> {children}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const cls = severity === 'HIGH' ? 'badge-high' : severity === 'MEDIUM' ? 'badge-medium' : 'badge-low';
  return <span className={`badge ${cls}`}>{severity}</span>;
}

export function EpistemicBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    OBSERVED: 'badge-green',
    NLP_EXTRACTED: 'badge-violet',
    INFERRED: 'badge-medium',
    RECOVERED: 'badge-medium',
  };
  return <span className={`badge ${map[status] || 'badge-low'}`}>{status}</span>;
}

export function StatCard({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="card-tight" style={{ minWidth: 140 }}>
      <div className="stat-number">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export interface ConnectorNode {
  label: string;
  value: string;
  metric?: string;
}

export function ConnectorChain({ nodes }: { nodes: ConnectorNode[] }) {
  return (
    <div className="connector-row">
      {nodes.map((n, i) => (
        <div key={i} style={{ display: 'flex', flex: 1, alignItems: 'stretch', minWidth: 0 }}>
          <div className="connector-card">
            <div className="card-label">{n.label}</div>
            <div className="card-value mono" title={n.value}>{n.value}</div>
            {n.metric && <div className="card-metric">{n.metric}</div>}
          </div>
          {i < nodes.length - 1 && (
            <div className="connector-link">
              <div className="line" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function FlagshipBanner({ children }: { children: ReactNode }) {
  return <div className="flagship-banner">★ {children}</div>;
}

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  PERSON: '#c4b8ff', PHONE: '#5fc082', ACCOUNT: '#e3a53f', VEHICLE: '#6a5cc4',
  LOCATION: '#e2685a', ORGANIZATION: '#a89fc4', CASE: '#ffffff',
};

export function EntityTypeIcon({ type }: { type: string }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: ENTITY_TYPE_COLORS[type] || '#a89fc4', marginRight: 6,
    }} />
  );
}
