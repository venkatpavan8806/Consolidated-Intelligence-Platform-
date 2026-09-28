import { useEffect, useState } from 'react';
import { api, type CaseTypeRow, ApiError } from '../api/client';
import { useCase } from '../context/CaseContext';
import { Eyebrow } from './common';

// Case-type confirmation UI: the "human always decides" step the
// classifier's suggestions feed into. A SUGGESTED row is a machine
// proposal only -- it must never be shown or treated as if it were
// confirmed, and confirming/rejecting is the only way a suggestion turns
// into something the rest of the system (case-type-scoped modules) can act
// on. A case can hold several CONFIRMED case types at once -- that's
// expected, not an error state.
const CASE_TYPE_LABELS: Record<string, string> = {
  FINANCIAL_FRAUD: 'Financial Fraud',
  TRAFFICKING_MISSING_PERSON: 'Trafficking / Missing Person',
  NARCOTICS: 'Narcotics',
  ASSAULT_HOMICIDE: 'Assault / Homicide',
  ROBBERY_THEFT: 'Robbery / Theft',
  ORGANIZED_CRIME: 'Organized Crime',
};

function label(caseType: string) {
  return CASE_TYPE_LABELS[caseType] || caseType;
}

export default function CaseTypePanel() {
  const { activeCase } = useCase();
  const [rows, setRows] = useState<CaseTypeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [classifying, setClassifying] = useState(false);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    if (!activeCase) return;
    setLoading(true);
    api.caseTypes(activeCase.case_id)
      .then(setRows)
      .catch(e => setError(e instanceof ApiError ? e.message : 'failed to load case types'))
      .finally(() => setLoading(false));
  }

  useEffect(load, [activeCase]);

  function runClassifier() {
    if (!activeCase) return;
    setClassifying(true);
    setError(null);
    api.classifyCase(activeCase.case_id)
      .then(load)
      .catch(e => setError(e instanceof ApiError ? e.message : 'classification failed'))
      .finally(() => setClassifying(false));
  }

  function decide(caseType: string, decision: 'CONFIRMED' | 'REJECTED') {
    if (!activeCase) return;
    const notes = decision === 'REJECTED'
      ? window.prompt(`Reason for rejecting "${label(caseType)}" (optional, for the audit trail):`) || undefined
      : undefined;
    setActingOn(caseType);
    setError(null);
    api.confirmCaseType(activeCase.case_id, caseType, decision, notes)
      .then(load)
      .catch(e => setError(e instanceof ApiError ? e.message : 'could not record decision'))
      .finally(() => setActingOn(null));
  }

  if (!activeCase) return null;

  const confirmed = rows.filter(r => r.status === 'CONFIRMED');
  const suggested = rows.filter(r => r.status === 'SUGGESTED');
  const rejected = rows.filter(r => r.status === 'REJECTED');

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <Eyebrow>Case Type</Eyebrow>
        <button className="btn" style={{ fontSize: 11.5 }} onClick={runClassifier} disabled={classifying}>
          {classifying ? 'Classifying…' : '↻ Re-run classifier'}
        </button>
      </div>

      {loading && <div style={{ color: 'var(--text-faint)', fontSize: 13, marginTop: 8 }}>Loading…</div>}
      {error && <div style={{ color: 'var(--badge-high, #e2685a)', fontSize: 12.5, marginTop: 8 }}>{error}</div>}

      {!loading && confirmed.length === 0 && suggested.length === 0 && (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, marginTop: 10 }}>
          No case type on record yet. Run the classifier to get a suggestion from the evidence already in this case
          -- an investigator still has to confirm it before anything acts on it.
        </div>
      )}

      {confirmed.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          {confirmed.map(r => (
            <span key={r.case_type} className="badge badge-green" title={r.reason || undefined}>
              ✓ {label(r.case_type)}
            </span>
          ))}
        </div>
      )}

      {suggested.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          {suggested.map(r => (
            <div key={r.case_type} className="card-tight" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {label(r.case_type)}
                  <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginLeft: 8 }}>
                    {r.confidence !== null ? `${Math.round(r.confidence * 100)}% confidence` : 'suggested'}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{r.reason}</div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn" style={{ fontSize: 11.5 }} disabled={actingOn === r.case_type}
                        onClick={() => decide(r.case_type, 'CONFIRMED')}>
                  Confirm
                </button>
                <button className="btn" style={{ fontSize: 11.5 }} disabled={actingOn === r.case_type}
                        onClick={() => decide(r.case_type, 'REJECTED')}>
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {rejected.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          {rejected.map(r => (
            <span key={r.case_type} className="badge badge-low" title={r.reason || undefined} style={{ opacity: 0.7 }}>
              ✕ {label(r.case_type)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
