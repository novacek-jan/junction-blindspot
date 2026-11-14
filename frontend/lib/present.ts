// Display helpers shared by the start page, results and side panel (design/claude).
import type { Industry, Source, Stage } from "./types";
import { formatDate, hostOf, stageLabel } from "./format";

const STAGE_ORDER = ["PRE_SEED", "SEED", "SERIES_A", "SERIES_B", "SERIES_C", "SERIES_D", "SERIES_E", "SERIES_F", "GROWTH"];

/** "Pre-seed to Series A" (or a single stage). */
export function stageRange(stages: Stage[]): string | null {
  if (!stages.length) return null;
  const rank = (s: Stage) => {
    const i = STAGE_ORDER.indexOf(s);
    return i === -1 ? STAGE_ORDER.length : i;
  };
  const sorted = [...stages].sort((a, b) => rank(a) - rank(b));
  const first = stageLabel(sorted[0]);
  const last = stageLabel(sorted[sorted.length - 1]);
  return first === last ? first : `${first} to ${last}`;
}

// Regions the backend widens a fund's countries to (docs/api-contract.md, thesis.countries).
const REGIONS: { name: string; countries: string[] }[] = [
  { name: "Nordics", countries: ["Denmark", "Finland", "Iceland", "Norway", "Sweden"] },
  { name: "DACH", countries: ["Germany", "Austria", "Switzerland", "Liechtenstein"] },
  { name: "Baltics", countries: ["Estonia", "Latvia", "Lithuania"] },
  { name: "Benelux", countries: ["Belgium", "Netherlands", "Luxembourg"] },
  { name: "UK & Ireland", countries: ["United Kingdom", "Ireland"] },
  { name: "France", countries: ["France", "Monaco"] },
  { name: "Iberia", countries: ["Spain", "Portugal"] },
];

/** "Nordics", "Nordics, DACH" or "Finland, Estonia +2": whole regions collapse to their name. */
export function regionLabel(countries: string[], max = 3): string | null {
  if (!countries.length) return null;
  const left = new Set(countries);
  const parts: string[] = [];
  for (const r of REGIONS) {
    if (r.countries.every((c) => left.has(c))) {
      parts.push(r.name);
      r.countries.forEach((c) => left.delete(c));
    }
  }
  parts.push(...countries.filter((c) => left.has(c)));
  return withMore(parts, max);
}

const SECTOR_SHORT: Record<string, string> = {
  SOFTWARE_AND_SERVICES: "software",
  INTERNET_AND_WEB_SERVICES: "internet",
  HARDWARE_AND_EQUIPMENT: "hardware",
  RENEWABLE_ENERGY: "energy",
  BIOTECHNOLOGY: "biotech",
  PHARMACEUTICALS: "pharma",
  HEALTHCARE_EQUIPMENT_AND_SERVICES: "health",
  HEALTH_CARE: "health",
  FINTECH: "fintech",
  BANKING: "banking",
  INSURANCE: "insurance",
  UTILITIES: "utilities",
  MANUFACTURING_AUTOMOTIVE: "automotive",
  MANUFACTURING: "manufacturing",
  RAW_MATERIALS: "materials",
  AGRICULTURE: "agriculture",
  AEROSPACE_AND_DEFENSE: "aerospace",
  CHEMICALS: "chemicals",
  LOGISTICS: "logistics",
  SEMICONDUCTORS: "semiconductors",
  TELECOMMUNICATIONS: "telecom",
  MEDIA_AND_ENTERTAINMENT: "media",
  CONSUMER_GOODS: "consumer",
  RETAIL: "retail",
  TRANSPORTATION: "mobility",
  REAL_ESTATE: "real estate",
  FOOD_AND_BEVERAGE: "food",
  EDUCATION: "education",
};

/**
 * "Software, internet, hardware, energy +2". `weight` (industry name -> count) puts the biggest sectors first;
 * without it the backend's order is kept.
 */
export function sectorLabel(industries: Industry[], max = 4, weight?: Map<string, number>): string | null {
  const ordered = weight ? [...industries].sort((a, b) => (weight.get(b.name) ?? 0) - (weight.get(a.name) ?? 0)) : industries;
  const names = [...new Set(ordered.map((i) => SECTOR_SHORT[i.code] ?? i.name.split(/\s+and\s+/i)[0].toLowerCase()))];
  const label = withMore(names, max);
  return label ? label[0].toUpperCase() + label.slice(1) : null;
}

/** Industry name -> how often it appears in `lists` (e.g. the never-seen companies' industries). */
export function industryWeights(lists: (string[] | undefined)[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const l of lists) for (const name of l ?? []) m.set(name, (m.get(name) ?? 0) + 1);
  return m;
}

function withMore(items: string[], max: number): string | null {
  if (!items.length) return null;
  const shown = items.slice(0, max).join(", ");
  return items.length > max ? `${shown} +${items.length - max}` : shown;
}

// Source chips: Filing (green), Company (blue), Press (grey), Aggregator (amber).
const SOURCE_CHIP: Record<string, { label: string; cls: string }> = {
  FILING: { label: "Filing", cls: "bg-mint-wash text-mint-ink" },
  PRIMARY: { label: "Company", cls: "bg-sky-wash text-sky-ink" },
  PRESS: { label: "Press", cls: "bg-chip text-muted" },
  AGGREGATOR: { label: "Aggregator", cls: "bg-agg-wash text-agg-ink" },
};

export function sourceChip(s: Source): { label: string; cls: string; domain: string } {
  const chip = SOURCE_CHIP[s.rank ?? ""] ?? { label: "Source", cls: "bg-chip text-muted" };
  return { ...chip, domain: s.url ? hostOf(s.url) : s.name };
}

/** "14 Nov 2026" */
export function longDate(iso: string | null | undefined): string | null {
  return iso ? formatDate(iso, true) : null;
}

export function monogram(name: string): string {
  return (name.match(/[A-Za-z0-9]/)?.[0] ?? "?").toUpperCase();
}
