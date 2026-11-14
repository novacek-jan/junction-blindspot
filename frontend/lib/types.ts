// Types mirror docs/api-contract.md (v1). Keep in sync with the contract.

export type SourceRank = "FILING" | "PRIMARY" | "PRESS" | "AGGREGATOR" | null;
export type Source = { name: string; url: string; rank: SourceRank };

export type Stage = string; // Cala codes: PRE_SEED, SEED, SERIES_A, ...
export type OrgRef = { id: string; name: string };

export type FundSearchResult = OrgRef;

export type FundProfile = {
  fund: OrgRef;
  investments_since_2022: number;
  stages: { label: Stage; share: number }[];
  countries: { name: string; count: number }[];
  industries: { name: string; count: number }[];
  suggested_peers: (OrgRef & { co_investments: number })[];
  sources: Source[];
};

export type NeverSeenDeal = {
  company_id: string;
  name: string;
  website: string;
  country: string;
  stage: Stage;
  amount: number;
  currency: string;
  date: string;
  lead_investors: OrgRef[];
  sources: Source[];
  conflated: boolean;
};

export type HeatmapCell = {
  country: string;
  stage: Stage;
  total: number;
  never_seen: number;
  share: number;
};

export type Audit = {
  audit_id: string;
  fund: OrgRef;
  peers: OrgRef[];
  simulated_crm: boolean;
  summary: {
    market_deals: number;
    in_pipeline: number;
    invested: number;
    passed: number;
    in_review: number;
    never_seen: number;
    coverage_pct: number;
  };
  venn: { pipeline_only: number; overlap: number; market_only: number };
  heatmap: { countries: string[]; stages: Stage[]; cells: HeatmapCell[] };
  top_blind_spots: { title: string; detail: string }[];
  never_seen_deals: NeverSeenDeal[];
  top_missed_leads: (OrgRef & { deals: number })[];
};

export type Round = {
  label: Stage;
  amount: number;
  currency: string;
  date: string | null; // the live backend sends null for some rounds (e.g. EU grants)
  lead_investors: OrgRef[];
  participants: OrgRef[];
  sources: Source[];
  conflated: boolean;
};

export type DealDetail = {
  id: string;
  name: string;
  website: string;
  description: string;
  country: string;
  founded: string;
  rounds: Round[];
  why_missed: { reason: string }[];
  recent_news: { title: string; date: string; source: string; url: string }[];
  sources: Source[];
};

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
