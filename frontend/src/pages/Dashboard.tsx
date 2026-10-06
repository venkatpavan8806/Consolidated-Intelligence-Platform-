import { useEffect, useState, useCallback } from 'react';
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { api, type GraphData, type Lead, type WomenSafetyData, type ReviewCluster } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useCase } from '../context/CaseContext';
import { Eyebrow } from '../components/common';
import Tour, { TOUR_STEPS, hasSeenTour, markTourSeen } from '../components/Tour';

export interface DashboardData {
  graph: GraphData;
  leads: Lead[];
  womenSafety: WomenSafetyData;
  reviewQueue: ReviewCluster[];
  reload: () => void;
}

export default function Dashboard() {
  const { caseId } = useParams();
  const { user, logout } = useAuth();
  const { activeCase, reason } = useCase();
  const navigate = useNavigate();

  const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [] });
  const [leads, setLeads] = useState<Lead[]>([]);
  const [womenSafety, setWomenSafety] = useState<WomenSafetyData>({
    leads: [], recruiters: [], transporters: [], repeat_locations: [], chain_candidates: [],
  });
  const [reviewQueue, setReviewQueue] = useState<ReviewCluster[]>([]);
  const [loading, setLoading] = useState(true);

  // Tour state lives here (Dashboard is the stable parent across nested
  // route changes) rather than inside <Tour>, which React may legitimately
  // unmount/remount as sibling content re-renders -- owning the state at
  // this level means tour progress survives that.
  const [tourActive, setTourActive] = useState(false);
  const [tourStep, setTourStep] = useState(0);

  const load = useCallback(() => {
    // Also guards against a stale/foreign case in context (e.g. the URL was
    // edited by hand, or context is left over from a different case) -- in
    // either case a fresh case selection with its own audit-logged reason
    // is required rather than silently reusing an unrelated one.
    if (!activeCase || !reason || activeCase.case_id !== caseId) {
      navigate('/cases');
      return;
    }
    setLoading(true);
    Promise.all([
      api.caseGraph(activeCase.case_id, reason),
      api.caseLeads(activeCase.case_id, reason),
      api.womenSafety(reason),
      api.reviewQueue(),
    ]).then(([g, l, ws, rq]) => {
      setGraph(g);
      setLeads(l);
      setWomenSafety(ws);
      setReviewQueue(rq);
      if (!hasSeenTour()) {
        markTourSeen();
        setTimeout(() => {
          setTourStep(0);
          setTourActive(true);
        }, 700);
      }
    }).finally(() => setLoading(false));
  }, [activeCase, reason, navigate, caseId]);

  useEffect(() => { load(); }, [load]);

  function startTour() {
    setTourStep(0);
    setTourActive(true);
  }
  function tourNext() {
    if (tourStep >= TOUR_STEPS.length - 1) setTourActive(false);
    else setTourStep(s => s + 1);
  }
  function tourBack() {
    setTourStep(s => Math.max(0, s - 1));
  }

  if (!activeCase) return null;

  const data: DashboardData = { graph, leads, womenSafety, reviewQueue, reload: load };

  const navItems = [
    { to: 'overview', label: 'Overview' },
    { to: 'graph', label: 'Graph', count: graph.nodes.length },
    { to: 'leads', label: 'Leads', count: leads.length },
    { to: 'review-queue', label: 'Review Queue', count: reviewQueue.length },
    { to: 'women-safety', label: 'Women Safety', count: womenSafety.leads.length, flagship: true },
    { to: 'evaluation', label: 'Self-Evaluation' },
    { to: 'audit', label: 'Audit Chain' },
  ];

  return (
    <div className="app-shell">
      <div className="app-panel" style={{ flexDirection: 'row' }}>

        <div style={{ width: 270, background: 'var(--card)', boxShadow: 'var(--shadow)', padding: '28px 18px', position: 'relative', zIndex: 1, flexShrink: 0, overflowY: 'auto' }}>
          <Eyebrow>Consolidated Intelligence Platform</Eyebrow>
          <div style={{ fontSize: 17, fontWeight: 600, margin: '8px 0 2px' }}>{activeCase.title}</div>
          <div className="mono" style={{ fontSize: 14, color: 'var(--text-faint)', marginBottom: 12 }}>{activeCase.case_id}</div>

          <button
            className="btn"
            style={{ width: '100%', fontSize: 16, marginBottom: 16 }}
            onClick={startTour}
          >
            Take a guided tour
          </button>

          <div className="nav-list">
            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={`/dashboard/${caseId}/${item.to}`}
                data-tour-nav={item.to}
                className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              >
                <span>{item.label}</span>
                {item.count !== undefined && <span className="count mono">{item.count}</span>}
              </NavLink>
            ))}
          </div>

          <div style={{ marginTop: 32, paddingTop: 8 }}>
            <div style={{ fontSize: 15, color: 'var(--text-dim)' }}>{user?.displayName}</div>
            <div className="mono" style={{ fontSize: 14, color: 'var(--text-faint)', marginBottom: 10 }}>{user?.role}</div>
            <button className="btn" style={{ width: '100%', fontSize: 15 }} onClick={() => navigate('/cases')}>
              Switch Case
            </button>
            <button className="btn" style={{ width: '100%', fontSize: 15, marginTop: 8 }} onClick={logout}>
              Sign Out
            </button>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, position: 'relative', zIndex: 1, padding: '32px 40px', overflowY: 'auto' }}>
          {loading ? <div style={{ color: 'var(--text-dim)' }}>Loading case workspace…</div> : <Outlet context={data} />}
        </div>
      </div>
      {!loading && (
        <Tour active={tourActive} step={tourStep} onNext={tourNext} onBack={tourBack} onClose={() => setTourActive(false)} />
      )}
    </div>
  );
}
