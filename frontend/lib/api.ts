// Single API client. NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json,
// otherwise requests go to NEXT_PUBLIC_API_URL (the backend). No keys live here.
import type { Audit, DealDetail, FundProfile, FundSearchResult } from "./types";
import fundsMock from "@/mocks/funds_search.json";
import profileMock from "@/mocks/fund_profile.json";
import auditMock from "@/mocks/audit.json";
import auditDemoMock from "@/mocks/audit_demo.json";
import dealDetailsMock from "@/mocks/deal_details.json";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(`Could not reach the API at ${API_URL}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {}
    throw new ApiError(`${res.status} ${detail}`, res.status);
  }
  return res.json() as Promise<T>;
}

const delay = <T>(value: T, ms = 250) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

export async function searchFunds(q: string): Promise<FundSearchResult[]> {
  if (USE_MOCKS) {
    const needle = q.trim().toLowerCase();
    return delay(
      (fundsMock as FundSearchResult[]).filter((f) => f.name.toLowerCase().includes(needle)).slice(0, 8),
      120,
    );
  }
  return http(`/api/funds/search?q=${encodeURIComponent(q)}`);
}

export async function getFundProfile(fundId: string): Promise<FundProfile> {
  if (USE_MOCKS) {
    const profile = profileMock as FundProfile;
    const fund = (fundsMock as FundSearchResult[]).find((f) => f.id === fundId) ?? profile.fund;
    return delay({
      ...profile,
      fund,
      suggested_peers: profile.suggested_peers.filter((p) => p.id !== fund.id),
    });
  }
  return http(`/api/funds/${encodeURIComponent(fundId)}/profile`);
}

export async function runAudit(input: { fundId: string; peerIds: string[]; crmCsv: File }): Promise<Audit> {
  if (USE_MOCKS) {
    const audit = auditMock as Audit;
    const funds = fundsMock as FundSearchResult[];
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
  if (USE_MOCKS) return delay(auditDemoMock as Audit, 300);
  return http("/api/audit/demo");
}

export async function getDeal(companyId: string, fundId: string): Promise<DealDetail> {
  if (USE_MOCKS) {
    const detail = (dealDetailsMock as Record<string, DealDetail>)[companyId];
    if (!detail) throw new ApiError("Deal not found in mocks", 404);
    return delay(detail, 300);
  }
  return http(`/api/deals/${encodeURIComponent(companyId)}?fund_id=${encodeURIComponent(fundId)}`);
}
