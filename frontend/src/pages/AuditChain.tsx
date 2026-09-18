import { useEffect, useState } from 'react';
import { api, type AuditEntry } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Eyebrow } from '../components/common';

const GENESIS_HASH = '0'.repeat(64);

async function sha256Hex(message: string): Promise<string> {
  const data = new TextEncoder().encode(message);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}

interface VerifiedEntry extends AuditEntry {
  browserHash: string;
  browserValid: boolean;
}

export default function AuditChain() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<VerifiedEntry[]>([]);
  const [backendValid, setBackendValid] = useState<boolean | null>(null);
  const [browserValid, setBrowserValid] = useState<boolean | null>(null);
  const [tamperTarget, setTamperTarget] = useState<{ seq: number; original_reason: string; original_payload_raw: string } | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const { entries: raw, verification } = await api.auditChain();
    setBackendValid(verification.valid);

    let expectedPrev = GENESIS_HASH;
    let allValid = true;
    const verified: VerifiedEntry[] = [];
    for (const e of raw) {
      const browserHash = await sha256Hex(`${e.prev_hash}|${e.payload_raw}`);
      const linkOk = e.prev_hash === expectedPrev;
      const hashOk = browserHash === e.hash;
      if (!linkOk || !hashOk) allValid = false;
      verified.push({ ...e, browserHash, browserValid: linkOk && hashOk });
      expectedPrev = e.hash;
    }
    setEntries(verified);
    setBrowserValid(allValid);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function runTamperDemo() {
    if (entries.length === 0) return;
    const target = entries[0];
    const result = await api.tamperDemo(target.seq, 'TAMPERED FOR DEMO — value altered without recomputing hash');
    setTamperTarget({ seq: target.seq, original_reason: result.original.reason, original_payload_raw: result.original.payload_raw });
    await load();
  }

  async function runRestore() {
    if (!tamperTarget) return;
    await api.restoreDemo(tamperTarget.seq, tamperTarget.original_reason, tamperTarget.original_payload_raw);
    setTamperTarget(null);
    await load();
  }

  return (
    <div>
      <Eyebrow>Tamper-Evident Audit Chain</Eyebrow>
      <h1 style={{ fontSize: 26, margin: '10px 0 6px' }}>Audit Chain</h1>
      <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 16, maxWidth: 780 }}>
        Every entry's hash = SHA-256(prev_hash + "|" + payload_raw). The backend verifies this in Python;
        the browser below independently re-hashes the exact raw string using Web Crypto SubtleCrypto — no
        shared trust between the two checks.
      </p>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div className="card-tight">
          <div className="card-label">Backend Verification (Python)</div>
          <div className={`badge ${backendValid ? 'badge-green' : 'badge-high'}`} style={{ marginTop: 6 }}>
            {backendValid === null ? '…' : backendValid ? 'CHAIN VALID' : 'TAMPERING DETECTED'}
          </div>
        </div>
        <div className="card-tight">
          <div className="card-label">Browser Verification (SubtleCrypto)</div>
          <div className={`badge ${browserValid ? 'badge-green' : 'badge-high'}`} style={{ marginTop: 6 }}>
            {browserValid === null ? '…' : browserValid ? 'CHAIN VALID' : 'TAMPERING DETECTED'}
          </div>
        </div>
      </div>

      {user?.role === 'admin' && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
          <button className="btn" onClick={runTamperDemo} disabled={!!tamperTarget}>
            Run Tamper Demo (mutate entry #{entries[0]?.seq ?? '?'})
          </button>
          <button className="btn btn-primary" onClick={runRestore} disabled={!tamperTarget}>
            Restore Entry
          </button>
        </div>
      )}

      {loading ? (
        <div style={{ color: 'var(--text-dim)' }}>Verifying chain…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.map(e => (
            <div key={e.seq} className="card-tight" style={{ borderColor: e.browserValid ? undefined : 'var(--red)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="mono" style={{ fontSize: 12.5 }}>#{e.seq} · {e.action} · {e.actor}</span>
                <span className={`badge ${e.browserValid ? 'badge-green' : 'badge-high'}`}>
                  {e.browserValid ? 'OK' : 'BROKEN'}
                </span>
              </div>
              <div style={{ fontSize: 13.5, color: 'var(--text-dim)', marginTop: 4 }}>{e.reason} {e.case_id ? `(${e.case_id})` : ''}</div>
              <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 6, wordBreak: 'break-all' }}>
                hash: {e.hash.slice(0, 24)}… · browser: {e.browserHash.slice(0, 24)}…
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
