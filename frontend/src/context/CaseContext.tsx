import { createContext, useContext, useState, type ReactNode } from 'react';
import type { CaseRow } from '../api/client';

interface CaseContextValue {
  activeCase: CaseRow | null;
  reason: string;
  setActiveCase: (c: CaseRow | null, reason: string) => void;
}

const CaseContext = createContext<CaseContextValue | null>(null);

const STORAGE_KEY = 'cip_case_context';

// Session-scoped (not localStorage): a case-query reason is tied to this
// login session and is meant to survive an accidental page refresh, not to
// outlive the browser tab or leak into a different investigator's session.
function loadPersisted(): { activeCase: CaseRow | null; reason: string } {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { activeCase: null, reason: '' };
    const parsed = JSON.parse(raw);
    return { activeCase: parsed.activeCase ?? null, reason: parsed.reason ?? '' };
  } catch {
    return { activeCase: null, reason: '' };
  }
}

export function CaseProvider({ children }: { children: ReactNode }) {
  const initial = loadPersisted();
  const [activeCase, setCase] = useState<CaseRow | null>(initial.activeCase);
  const [reason, setReason] = useState(initial.reason);

  function setActiveCase(c: CaseRow | null, r: string) {
    setCase(c);
    setReason(r);
    try {
      if (c) sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ activeCase: c, reason: r }));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // sessionStorage unavailable (private mode, etc.) -- context still
      // works for the current page lifetime, it just won't survive a refresh
    }
  }

  return <CaseContext.Provider value={{ activeCase, reason, setActiveCase }}>{children}</CaseContext.Provider>;
}

export function useCase() {
  const ctx = useContext(CaseContext);
  if (!ctx) throw new Error('useCase must be used within CaseProvider');
  return ctx;
}
