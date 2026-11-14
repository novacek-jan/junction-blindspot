// Single API client. NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json,
// otherwise requests go to NEXT_PUBLIC_API_URL (the backend). No keys live here.
import { isAudit, type Audit, type CrmMapping, type CrmPreview, type FundProfile, type FundSearchResult } from "./types";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 15_000;

export type ApiErrorKind =
  | "auth"
  | "too_large"
  | "bad_format"
  | "no_company"
  | "invalid_mapping"
  | "unreadable"
  | "rate_limited"
  | "live_off"
  | "unavailable"
  | "timeout"
  | "not_found"
  | "other";

export const ERROR_MESSAGES: Record<ApiErrorKind, string> = {
  auth: "Invalid access code.",
  too_large: "File too large. Max 2 MB and 5,000 rows.",
  bad_format: "Upload a .csv or .xlsx file. Legacy .xls and macro workbooks are not supported.",
  no_company: "No company or website column found in this file.",
  invalid_mapping: "Those columns don't match this file. Pick them again.",
  unreadable: "We couldn't read this file.",
  rate_limited: "Too many requests, try again in a minute.",
  live_off: "Live audits are temporarily unavailable. Try the demo instead.",
  unavailable: "Backend unavailable. Try the demo instead.",
  timeout: "No response after 15 seconds. Try the demo instead.",
  not_found: "Not found.",
  other: "Something went wrong. Please try again.",
};

/** Errors after which "Run the demo" is offered. */
export const DEMO_FALLBACK: ReadonlySet<ApiErrorKind> = new Set(["live_off", "unavailable", "timeout"]);

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind, public status?: number) {
    super(ERROR_MESSAGES[kind]);
  }
}

/** Maps a status (and the backend's `error` code from `{ error, detail }`) to a message. */
export function errorKindFor(status: number, code?: string): ApiErrorKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 413) return "too_large";
  if (status === 415) return "bad_format";
  if (status === 422) return code === "invalid_mapping" ? "invalid_mapping" : code === "no_company_column" ? "no_company" : "unreadable";
  if (status === 429) return "rate_limited";
  if (status === 404) return "not_found";
  if (status === 503) return "live_off";
  if (status >= 500) return "unavailable";
  return "other";
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
  } catch {
    // No response within REQUEST_TIMEOUT_MS, or a network/CORS failure.
    throw new ApiError(controller.signal.aborted ? "timeout" : "unavailable");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const code = await res.json().then((b: { error?: unknown }) => (typeof b?.error === "string" ? b.error : undefined), () => undefined);
    throw new ApiError(errorKindFor(res.status, code), res.status);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("unavailable", res.status);
  }
}

/**
 * Mock mode only: simulate backend errors on the upload preview via the page URL,
 * e.g. /?mockError=401 | 413 | 415 | 422 | invalid_mapping | 429 | 503 | 500 | network.
 */
function mockUploadError(): ApiError | null {
  if (typeof window === "undefined") return null;
  const v = new URLSearchParams(window.location.search).get("mockError");
  if (!v) return null;
  if (v === "network") return new ApiError("unavailable");
  if (v === "invalid_mapping") return new ApiError("invalid_mapping", 422);
  const status = Number(v);
  return Number.isInteger(status) && status >= 400 ? new ApiError(errorKindFor(status, status === 422 ? "no_company_column" : undefined), status) : null;
}

// Mocks are loaded lazily so a build with NEXT_PUBLIC_USE_MOCKS!=true does not ship them.
const mocks = {
  funds: () => import("@/mocks/funds_search.json").then((m) => m.default as FundSearchResult[]),
  profile: () => import("@/mocks/fund_profile.json").then((m) => m.default as FundProfile),
  audit: () => import("@/mocks/audit.json").then((m) => m.default as Audit),
  preview: () => import("@/mocks/audit_preview.json").then((m) => m.default as CrmPreview),
  demo: () => import("@/mocks/audit_demo.json").then((m) => m.default as Audit),
};

const delay = <T>(value: T, ms = 250) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

// Fund search results per query, so typing back and forth does not refetch (the list is ~90 funds).
const searchCache = new Map<string, Promise<FundSearchResult[]>>();

export function searchFunds(q: string): Promise<FundSearchResult[]> {
  const key = q.trim().toLowerCase();
  let hit = searchCache.get(key);
  if (!hit) {
    hit = fetchFunds(key);
    searchCache.set(key, hit);
    hit.catch(() => searchCache.delete(key));
  }
  return hit;
}

async function fetchFunds(q: string): Promise<FundSearchResult[]> {
  if (USE_MOCKS) {
    const needle = q.trim().toLowerCase();
    const funds = await mocks.funds();
    return delay(funds.filter((f) => f.name.toLowerCase().includes(needle)).slice(0, 8), 120);
  }
  return http(`/api/funds/search?q=${encodeURIComponent(q)}`);
}

export async function getFundProfile(fundId: string): Promise<FundProfile> {
  if (USE_MOCKS) {
    const [profile, funds] = await Promise.all([mocks.profile(), mocks.funds()]);
    const fund = funds.find((f) => f.id === fundId) ?? profile.fund;
    return delay({ ...profile, fund });
  }
  return http(`/api/funds/${encodeURIComponent(fundId)}/profile`);
}

function uploadForm(file: File, mapping?: CrmMapping | null): FormData {
  const form = new FormData();
  form.append("crm_csv", file); // sent with the browser's own content type; the backend detects .csv/.xlsx itself
  if (mapping) form.append("mapping", JSON.stringify(mapping));
  return form;
}

function accessHeaders(accessCode?: string): HeadersInit | undefined {
  const code = accessCode?.trim();
  return code ? { "X-Access-Code": code } : undefined;
}

export async function previewCrm(input: { file: File; mapping?: CrmMapping | null; accessCode?: string }): Promise<CrmPreview> {
  if (USE_MOCKS) {
    const simulated = mockUploadError();
    if (simulated) {
      await delay(null, 400);
      throw simulated;
    }
    const preview = await mocks.preview();
    const mapping = input.mapping ?? preview.mapping;
    return delay({ ...preview, file_type: /\.xlsx$/i.test(input.file.name) ? "xlsx" : "csv", mapping }, 400);
  }
  return http("/api/audit/preview", {
    method: "POST",
    body: uploadForm(input.file, input.mapping),
    headers: accessHeaders(input.accessCode),
  });
}

export async function runAudit(input: {
  fundId: string;
  crmFile: File;
  mapping?: CrmMapping | null;
  accessCode?: string;
}): Promise<Audit> {
  if (USE_MOCKS) {
    const [audit, funds] = await Promise.all([mocks.audit(), mocks.funds()]);
    const fund = funds.find((f) => f.id === input.fundId) ?? audit.fund;
    return delay({ ...audit, fund: { id: fund.id, name: fund.name } }, 900);
  }
  const form = uploadForm(input.crmFile, input.mapping);
  form.append("fund_id", input.fundId);
  return checkAudit(await http("/api/audit", { method: "POST", body: form, headers: accessHeaders(input.accessCode) }));
}

// A response without the v2 fields cannot be rendered: report it like an unavailable backend.
function checkAudit(a: unknown): Audit {
  if (!isAudit(a)) throw new ApiError("unavailable");
  return a;
}

export async function getDemoAudit(): Promise<Audit> {
  if (USE_MOCKS) return delay(await mocks.demo(), 300);
  return checkAudit(await http("/api/audit/demo"));
}

/** Rejects with a timeout error if `p` takes longer than REQUEST_TIMEOUT_MS (also covers mock mode and navigation). */
export function withTimeout<T>(p: Promise<T>, ms = REQUEST_TIMEOUT_MS): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new ApiError("timeout")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}
