import type { Audit } from "./types";

// Hand-off of the latest audit from "/" to "/results" within the browser tab.
const KEY = "blindspot:audit";

export function saveAudit(audit: Audit) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(audit));
  } catch {}
}

export function loadAudit(): Audit | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Audit) : null;
  } catch {
    return null;
  }
}
