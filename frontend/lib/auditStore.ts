import { isAudit, type Audit } from "./types";

/**
 * Hand-off of an audit from "/" to "/results".
 *
 * - A real upload is stored in sessionStorage with `fromUpload: true`, so a reload of /results in the same tab
 *   still shows it. Nothing else is ever persisted.
 * - The demo is never persisted: "/" hands it over in memory (one read), and /results otherwise fetches it fresh.
 * - The key carries a version suffix; audits stored by older builds (other keys) are ignored and removed.
 */
const VERSION = "v3";
const KEY = `blindspot:audit:${VERSION}`;
const LEGACY_KEYS = ["blindspot:audit", "blindspot:audit:v2"];

type Stored = { v: typeof VERSION; fromUpload: true; audit: Audit };

let memoryDemo: Audit | null = null;

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function dropLegacy(s: Storage) {
  for (const k of LEGACY_KEYS) {
    try {
      s.removeItem(k);
    } catch {}
  }
}

/** Stores the audit returned by POST /api/audit for this tab (replaces any earlier one). */
export function saveUploadedAudit(audit: Audit) {
  memoryDemo = null;
  const s = storage();
  if (!s) return;
  dropLegacy(s);
  try {
    s.setItem(KEY, JSON.stringify({ v: VERSION, fromUpload: true, audit } satisfies Stored));
  } catch {}
}

/** The audit from a real upload in this tab, or null. */
export function loadUploadedAudit(): Audit | null {
  const s = storage();
  if (!s) return null;
  dropLegacy(s);
  try {
    const raw = s.getItem(KEY);
    const stored: unknown = raw ? JSON.parse(raw) : null;
    if (
      stored &&
      typeof stored === "object" &&
      (stored as Stored).v === VERSION &&
      (stored as Stored).fromUpload === true &&
      isAudit((stored as Stored).audit)
    ) {
      return (stored as Stored).audit;
    }
    s.removeItem(KEY);
  } catch {}
  return null;
}

/** Drops the stored upload when the API returned a different audit (e.g. a fresh demo was loaded instead). */
export function dropIfDifferent(auditId: string) {
  const stored = loadUploadedAudit();
  if (stored && stored.audit_id !== auditId) clearAudit();
}

export function clearAudit() {
  memoryDemo = null;
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(KEY);
  } catch {}
}

/** In-memory hand-off of a demo just fetched on "/" (consumed once, never persisted). */
export function handOffDemo(audit: Audit) {
  clearAudit();
  memoryDemo = audit;
}

export function takeDemo(): Audit | null {
  const a = memoryDemo;
  memoryDemo = null;
  return a;
}
