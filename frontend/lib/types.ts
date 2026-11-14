// Types mirror docs/api-contract.md (v2). Keep in sync with the contract.

export type SourceRank = "FILING" | "PRIMARY" | "PRESS" | "AGGREGATOR" | null;
export type Source = { name: string; url: string; rank: SourceRank; date?: string | null };

export type Stage = string; // Cala codes: PRE_SEED, SEED, SERIES_A, ...
export type OrgRef = { id: string; name: string };

// basis_rounds: not in the contract yet; shown as "based on N rounds" when the backend sends it.
export type FundSearchResult = OrgRef & { basis_rounds?: number };

export type Industry = { code: string; name: string };
export type Thesis = { stages: Stage[]; countries: string[]; industries: Industry[] };

export type FundProfile = {
  fund: OrgRef;
  investments_since_2022: number;
  stages: { label: Stage; share: number }[];
  countries: { name: string; count: number }[];
  industries: { name: string; count: number }[];
  thesis?: Thesis;
  sources: Source[];
};

export type Investor = { id: string; name: string; type?: string; is_lead: boolean; is_vc?: boolean };

export type BlindSpot = {
  company_id: string;
  name: string;
  website?: string | null;
  country: string | null;
  industries?: string[];
  round: {
    id: string;
    label: Stage | null;
    amount: number | null;
    currency: string | null;
    date: string | null;
    date_kind?: "announcement" | "event";
    investors: Investor[];
    sources: Source[];
  };
};

export type Audit = {
  audit_id: string;
  fund: OrgRef;
  simulated_crm: boolean;
  period: { from: string; to: string };
  thesis: Thesis & { basis_rounds: number };
  headline: { never_seen: number; text: string };
  summary: {
    market_companies: number;
    in_crm: number;
    invested: number;
    passed: number;
    in_review: number;
    never_seen: number;
    coverage_pct: number;
  };
  never_seen: BlindSpot[];
  top_investors_in_blind_spots: (OrgRef & { companies: number })[];
  market_coverage: {
    european_companies_screened: number;
    qualifying_companies: number;
    investors_explored: number;
    as_of: string;
    region?: string; // crawl focus code, e.g. "nordics"
    region_countries?: string[];
    region_qualifying_companies?: number;
    priority_country?: string;
    priority_country_qualifying_companies?: number;
  };
  // Newer fields: the page renders without them.
  breakdown?: BreakdownCell[];
  patterns?: Pattern[];
};

/** One thesis country × thesis stage: `market` companies, of which `never_seen`. */
export type BreakdownCell = { country: string; stage: Stage; market: number; never_seen: number };
export type Pattern = { kind: string; text: string; value: number; total: number };

export type DemoEntry = { fund: OrgRef; default: boolean };

export type DealRound = {
  id: string;
  label: Stage | null;
  amount: number | null;
  currency: string | null;
  date: string | null; // null e.g. for EU grants without a date
  date_kind?: "announcement" | "event";
  qualifying?: boolean;
  lead_investors: OrgRef[];
  participants: OrgRef[];
  sources: Source[];
  conflated?: boolean;
};

export type DealDetail = {
  id: string;
  name: string;
  website?: string | null;
  description?: string | null;
  country?: string | null;
  founded?: string | null;
  rounds: DealRound[];
  recent_news?: { title: string; date: string | null; source: string; url: string }[];
  sources: Source[];
};

/** True for a v2 audit response (the shape the UI renders). */
export function isAudit(a: unknown): a is Audit {
  const x = a as Audit | null;
  return !!x && Array.isArray(x.never_seen) && typeof x.headline?.text === "string" && !!x.thesis && !!x.market_coverage;
}

// POST /api/audit/preview
export type CrmField = "company" | "website" | "status" | "date";
export type CrmMapping = Record<CrmField, string | null>;
export type CrmPreview = {
  file_type: "csv" | "xlsx";
  columns: string[];
  mapping: CrmMapping;
  row_count: number;
  skipped_rows: number;
  matched_rows: number | null; // null when the backend has no live data
  status_counts: Record<"invested" | "passed" | "in_review" | "seen", number>;
  sample_rows: {
    company: string;
    website: string | null;
    status: string;
    raw_status: string | null;
    date: string | null;
    matched: boolean;
  }[];
  warnings: string[];
};
