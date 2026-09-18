import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

export interface TourStep {
  navKey: string;
  title: string;
  body: string;
}

// Mirrors the "Guided Walkthrough" section of the printed Investigator
// Briefing Guide, so the in-app tour and the handout tell the same story.
export const TOUR_STEPS: TourStep[] = [
  {
    navKey: 'overview',
    title: 'Overview',
    body: 'The case at a glance: how many people/phones/accounts are involved, how many leads have been found, and the highest-severity findings. Start here for a thirty-second summary.',
  },
  {
    navKey: 'graph',
    title: 'Graph Explorer',
    body: 'The relationship map. Colour = entity type. A red ring means that entity is deliberately excluded from every ranking (an officer’s own phone, or a customer-care number). Click any dot to see the evidence behind it.',
  },
  {
    navKey: 'leads',
    title: 'Leads',
    body: 'Every pattern the system found, in plain language, with the exact source records behind it. Mark each one Useful / Already Known / Wrong Person — the system never closes this loop itself.',
  },
  {
    navKey: 'review-queue',
    title: 'Review Queue',
    body: 'Cases where two similarly-named mentions could NOT be confirmed as the same person from the records alone. The system asks a human here instead of guessing.',
  },
  {
    navKey: 'women-safety',
    title: 'Women Safety (flagship)',
    body: 'The trafficking-network view: recruiter and transporter candidates, plus a repeated-location signal. It reuses the exact same detection machinery as the financial-fraud view.',
  },
  {
    navKey: 'evaluation',
    title: 'Self-Evaluation',
    body: 'The system grading its own work — which planted scenarios it caught, extraction confidence, and an honestly-reported accuracy number for its hardest feature.',
  },
  {
    navKey: 'audit',
    title: 'Audit Chain',
    body: 'Every query and decision, chained with cryptographic hashes so tampering is detectable — verified independently by the server and by your browser.',
  },
];

const SEEN_KEY = 'cip_tour_seen';

export function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return true;
  }
}

export function markTourSeen() {
  try {
    localStorage.setItem(SEEN_KEY, '1');
  } catch {
    // localStorage unavailable -- tour will simply auto-start again next time
  }
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface TourProps {
  active: boolean;
  step: number;
  onNext: () => void;
  onBack: () => void;
  onClose: () => void;
}

/**
 * Purely presentational: all "is the tour running / which step" state lives
 * in Dashboard (the stable parent across route changes) and is passed in as
 * props. This component may itself be unmounted/remounted by React without
 * losing tour progress, since it owns none of that state itself -- only the
 * derived spotlight rectangle, which is cheap to recompute.
 */
export default function Tour({ active, step, onNext, onBack, onClose }: TourProps) {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    if (!active) {
      setRect(null);
      return;
    }
    const current = TOUR_STEPS[step];
    navigate(`/dashboard/${caseId}/${current.navKey}`);

    const measure = () => {
      const el = document.querySelector(`[data-tour-nav="${current.navKey}"]`) as HTMLElement | null;
      if (el) {
        const r = el.getBoundingClientRect();
        setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
      }
    };
    measure();
    const t = setTimeout(measure, 80);
    window.addEventListener('resize', measure);
    return () => {
      clearTimeout(t);
      window.removeEventListener('resize', measure);
    };
  }, [active, step, caseId, navigate]);

  if (!active || !rect) return null;

  const PAD = 6;
  const top = rect.top - PAD;
  const left = rect.left - PAD;
  const width = rect.width + PAD * 2;
  const height = rect.height + PAD * 2;
  const dim = 'rgba(5,4,10,0.72)';
  const current = TOUR_STEPS[step];
  const isLast = step === TOUR_STEPS.length - 1;

  const tooltipWidth = 320;
  const tooltipLeft = Math.min(left + width + 16, window.innerWidth - tooltipWidth - 16);
  const tooltipTop = Math.max(16, Math.min(top + height / 2 - 90, window.innerHeight - 230));

  return (
    <>
      {/* four dimming panels around the spotlighted nav item */}
      <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: Math.max(0, top), background: dim, zIndex: 9998 }} onClick={onClose} />
      <div style={{ position: 'fixed', top: top + height, left: 0, width: '100vw', height: `calc(100vh - ${top + height}px)`, background: dim, zIndex: 9998 }} onClick={onClose} />
      <div style={{ position: 'fixed', top, left: 0, width: Math.max(0, left), height, background: dim, zIndex: 9998 }} onClick={onClose} />
      <div style={{ position: 'fixed', top, left: left + width, width: `calc(100vw - ${left + width}px)`, height, background: dim, zIndex: 9998 }} onClick={onClose} />

      {/* spotlight ring */}
      <div style={{
        position: 'fixed', top, left, width, height, zIndex: 9999, pointerEvents: 'none',
        border: '2px solid var(--violet)', borderRadius: 12,
        boxShadow: '0 0 0 4px rgba(156,140,245,0.25), 0 0 24px rgba(156,140,245,0.55)',
      }} />

      {/* tooltip card */}
      <div className="card" style={{
        position: 'fixed', top: tooltipTop, left: tooltipLeft, width: tooltipWidth, zIndex: 10000,
        borderColor: 'var(--violet)',
      }}>
        <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
          <span>STEP {step + 1} OF {TOUR_STEPS.length}</span>
          <span onClick={onClose} style={{ cursor: 'pointer' }}>SKIP TOUR ✕</span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8 }}>{current.title}</div>
        <div style={{ fontSize: 13.5, color: 'var(--text-dim)', lineHeight: 1.5, marginBottom: 16 }}>{current.body}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}>
          <button className="btn" style={{ fontSize: 12.5, opacity: step === 0 ? 0.4 : 1 }} onClick={onBack} disabled={step === 0}>
            Back
          </button>
          <div style={{ display: 'flex', gap: 4 }}>
            {TOUR_STEPS.map((_, i) => (
              <span key={i} style={{
                width: 6, height: 6, borderRadius: '50%',
                background: i === step ? 'var(--violet)' : 'var(--line)',
              }} />
            ))}
          </div>
          <button className="btn btn-primary" style={{ fontSize: 12.5 }} onClick={onNext}>
            {isLast ? 'Finish' : 'Next'}
          </button>
        </div>
      </div>
    </>
  );
}
