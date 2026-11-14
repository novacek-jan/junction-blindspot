// Single API client. NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json,
// otherwise requests go to NEXT_PUBLIC_API_URL (the backend). No keys live here.
import type { Audit, DealDetail, FundProfile, FundSearchResult } from "./types";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(
        `The Blindspot server did not respond within ${REQUEST_TIMEOUT_MS / 1000} seconds. Try again, or use the demo.`,
        408,
      );
    }
    throw new ApiError("Could not reach the Blindspot server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {}
    throw new ApiError(`Request failed (${res.status}${detail ? `: ${detail}` : ""}).`, res.status);
  }
  return res.json() as Promise<T>;
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

export async function runAudit(input: { fundId: string; peerIds: string[]; crmCsv: File }): Promise<Audit> {
  if (USE_MOCKS) {
    const [audit, funds] = await Promise.all([mocks.audit(), mocks.funds()]);
    const fund = funds.find((f) => f.id === input.fundId) ?? audit.fund;
    const peers = input.peerIds.map((id) => funds.find((f) => f.id === id)).filter(Boolean) as FundSearchResult[];
    return delay({ ...audit, fund, peers: peers.length ? peers : audit.peers }, 900);
  }
  const form = new FormData();
  form.append("fund_id", input.fundId);
  form.append("peer_ids", input.peerIds.join(","));
  form.append("crm_csv", input.crmCsv);
  return http("/api/audit", { method: "POST", body: form });
}

export async function getDemoAudit(): Promise<Audit> {
  if (USE_MOCKS) return delay(await mocks.demo(), 300);
  return http("/api/audit/demo");
}

export async function getDeal(companyId: string, fundId: string): Promise<DealDetail> {
  if (USE_MOCKS) {
    const detail = (await mocks.deals())[companyId];
    if (!detail) throw new ApiError("Deal not found in mocks", 404);
    return delay(detail, 300);
  }
  return http(`/api/deals/${encodeURIComponent(companyId)}?fund_id=${encodeURIComponent(fundId)}`);
}
