import { isAudit, type Audit } from "./types";

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
    const audit: unknown = raw ? JSON.parse(raw) : null;
    return isAudit(audit) ? audit : null; // ignores an audit stored by an older version of the app
  } catch {
    return null;
  }
}

export function clearAudit() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {}
}
