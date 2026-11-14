// Single API client. NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json,
// otherwise requests go to NEXT_PUBLIC_API_URL (the backend). No keys live here.
import type { Audit, DealDetail, FundProfile, FundSearchResult } from "./types";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 15_000;

export type ApiErrorKind = "auth" | "invalid_csv" | "rate_limited" | "unavailable" | "not_found" | "other";

export const ERROR_MESSAGES: Record<ApiErrorKind, string> = {
  auth: "Invalid access code.",
  invalid_csv: "CSV too large or invalid. Max 2 MB and 5,000 rows.",
  rate_limited: "Too many audits, try again in a minute.",
  unavailable: "Backend unavailable. Try the demo instead.",
  not_found: "Not found.",
  other: "Something went wrong. Please try again.",
};

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind, public status?: number) {
    super(ERROR_MESSAGES[kind]);
  }
}

export function errorKindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 413 || status === 415 || status === 422) return "invalid_csv";
  if (status === 429) return "rate_limited";
  if (status === 404) return "not_found";
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
    // Network error, CORS failure or no response within REQUEST_TIMEOUT_MS.
    throw new ApiError("unavailable");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw new ApiError(errorKindForStatus(res.status), res.status);
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("unavailable", res.status);
  }
}

/**
 * Mock mode only: simulate backend errors on POST /api/audit via the page URL,
 * e.g. /?mockError=401 | 413 | 422 | 429 | 500 | network.
 */
function mockAuditError(): ApiError | null {
  if (typeof window === "undefined") return null;
  const v = new URLSearchParams(window.location.search).get("mockError");
  if (!v) return null;
  if (v === "network") return new ApiError("unavailable");
  const status = Number(v);
  return Number.isInteger(status) && status >= 400 ? new ApiError(errorKindForStatus(status), status) : null;
}

// Mocks are loaded lazily so a build with NEXT_PUBLIC_USE_MOCKS!=true does not ship them.
const mocks = {
  funds: () => import("@/mocks/funds_search.json").then((m) => m.default as FundSearchResult[]),
  profile: () => import("@/mocks/fund_profile.json").then((m) => m.default as FundProfile),
  audit: () => import("@/mocks/audit.json").then((m) => m.default as Audit),
  demo: () => import("@/mocks/audit_demo.json").then((m) => m.default as Audit),
  deals: () => import("@/mocks/deal_details.json").then((m) => m.default as Record<string, DealDetail>),
};

const delay = <T>(value: T, ms = 250) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

export async function searchFunds(q: string): Promise<FundSearchResult[]> {
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
    return delay({ ...profile, fund, suggested_peers: profile.suggested_peers.filter((p) => p.id !== fund.id) });
  }
  return http(`/api/funds/${encodeURIComponent(fundId)}/profile`);
}

export async function runAudit(input: {
  fundId: string;
  peerIds: string[];
  crmCsv: File;
  accessCode?: string;
}): Promise<Audit> {
  if (USE_MOCKS) {
    const simulated = mockAuditError();
    if (simulated) {
      await delay(null, 600);
      throw simulated;
    }
    const [audit, funds] = await Promise.all([mocks.audit(), mocks.funds()]);
    const fund = funds.find((f) => f.id === input.fundId) ?? audit.fund;
    const peers = input.peerIds.map((id) => funds.find((f) => f.id === id)).filter(Boolean) as FundSearchResult[];
    return delay({ ...audit, fund, peers: peers.length ? peers : audit.peers }, 900);
  }
  const form = new FormData();
  form.append("fund_id", input.fundId);
  form.append("peer_ids", input.peerIds.join(","));
  // The backend only accepts text/csv; browsers report CSVs as "", text/plain or application/vnd.ms-excel.
  form.append("crm_csv", new File([input.crmCsv], input.crmCsv.name, { type: "text/csv" }));
  const code = input.accessCode?.trim();
  return http("/api/audit", {
    method: "POST",
    body: form,
    headers: code ? { "X-Access-Code": code } : undefined,
  });
}

export async function getDemoAudit(): Promise<Audit> {
  if (USE_MOCKS) return delay(await mocks.demo(), 300);
  return http("/api/audit/demo");
}

export async function getDeal(companyId: string, fundId: string): Promise<DealDetail> {
  if (USE_MOCKS) {
    const detail = (await mocks.deals())[companyId];
    if (!detail) throw new ApiError("not_found", 404);
    return delay(detail, 300);
  }
  return http(`/api/deals/${encodeURIComponent(companyId)}?fund_id=${encodeURIComponent(fundId)}`);
}
