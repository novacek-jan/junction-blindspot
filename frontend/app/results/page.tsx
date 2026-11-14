"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell, CalaBadge, SimulatedCrmBadge } from "@/components/AppShell";
import { DealsTable } from "@/components/DealsTable";
import { DealPanel } from "@/components/DealPanel";
import { Icon } from "@/components/Icon";
import { BreakdownMatrix } from "@/components/BreakdownMatrix";
import { KeyPatterns } from "@/components/KeyPatterns";
import { ApiError, ERROR_MESSAGES, getDemoAudit, getDemos, withTimeout } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import { formatDate, stageLabel } from "@/lib/format";
import type { Audit, BlindSpot, DemoEntry } from "@/lib/types";

export default function ResultsPage() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<BlindSpot | null>(null);
  const closePanel = useCallback(() => setOpen(null), []);

  useEffect(() => {
    // Audit handed over from "/"; on a direct visit load the default demo.
    let cancelled = false;
    const stored = loadAudit();
    (stored ? Promise.resolve(stored) : withTimeout(getDemoAudit()))
      .then((a) => {
        if (cancelled) return;
        saveAudit(a);
        setAudit(a);
      })
      .catch((e) => !cancelled && setError(loadError(e)));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (error) {
    return (
      <AppShell crumb="Results">
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
          <p role="alert" className="text-xl font-semibold text-ink">
            {error}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
              className="h-11 rounded-lg bg-ink px-5 text-base font-semibold text-white hover:bg-ink-hover"
            >
              Retry
            </button>
            <Link href="/" className="flex h-11 items-center rounded-lg border border-slate-200 bg-white px-5 text-base font-semibold hover:bg-slate-50">
              Back
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  if (!audit) {
    return (
      <AppShell crumb="Results">
        <ResultsSkeleton />
      </AppShell>
    );
  }

  const { summary: s, thesis } = audit;

  return (
    <AppShell
      crumb={audit.fund.name}
      right={
        <>
          <CalaBadge />
          {audit.simulated_crm ? <SimulatedCrmBadge /> : null}
        </>
      }
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8 sm:px-10 sm:py-10 2xl:max-w-[1520px] 2xl:gap-10">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="text-3xl font-bold tracking-tight text-ink 2xl:text-4xl">{audit.fund.name}</h1>
            {audit.simulated_crm ? (
              <DemoSwitch
                current={audit.fund.id}
                onLoaded={(a) => {
                  saveAudit(a);
                  setAudit(a);
                }}
              />
            ) : null}
          </div>
          <ThesisChips thesis={thesis} />
          <p className="text-base text-zinc-600 2xl:text-lg">
            Thesis based on <span className="tabular font-semibold text-ink">{thesis.basis_rounds.toLocaleString("en-US")}</span> rounds since 2022
          </p>
        </div>

        <Hero neverSeen={s.never_seen} market={s.market_companies} />
        <Stats audit={audit} />

        <BreakdownAndPatterns audit={audit} />

        <DealsTable rows={audit.never_seen} onOpen={setOpen} />

        <p className="text-sm text-zinc-500 2xl:text-base">{marketLine(audit)}</p>
      </div>
      {open ? <DealPanel row={open} fundId={audit.fund.id} onClose={closePanel} /> : null}
    </AppShell>
  );
}

// Side by side when both exist, otherwise the one that exists takes the full width.
function BreakdownAndPatterns({ audit }: { audit: Audit }) {
  const hasMatrix = (audit.breakdown ?? []).some((c) => c.market > 0);
  const hasPatterns = (audit.patterns ?? []).length > 0;
  if (!hasMatrix && !hasPatterns) return null;
  return (
    <div className={`grid grid-cols-1 items-start gap-8 ${hasMatrix && hasPatterns ? "xl:grid-cols-[3fr_2fr]" : ""}`}>
      {hasMatrix ? <BreakdownMatrix cells={audit.breakdown!} /> : null}
      {hasPatterns ? <KeyPatterns patterns={audit.patterns!} /> : null}
    </div>
  );
}

function loadError(e: unknown): string {
  // The demo itself failed here, so don't suggest trying it.
  const kind = e instanceof ApiError ? e.kind : "other";
  return kind === "timeout" ? "No response after 15 seconds." : kind === "unavailable" || kind === "live_off" ? "Backend unavailable." : ERROR_MESSAGES[kind];
}

/** Whole-number shares of the thesis market that add up to 100. */
function shares(neverSeen: number, market: number) {
  if (market <= 0) return { blind: 0, captured: 0 };
  const blind = Math.round((100 * neverSeen) / market);
  return { blind, captured: 100 - blind };
}

function Hero({ neverSeen, market }: { neverSeen: number; market: number }) {
  const { blind } = shares(neverSeen, market);
  return (
    <section className="flex flex-col gap-5 rounded-xl border border-slate-200/80 bg-white p-8 shadow-card 2xl:p-10">
      <span className="inline-flex w-fit items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5">
        <span className="size-2 rounded-full bg-sky-600" />
        <span className="tabular text-base font-bold uppercase tracking-wider text-sky-700 2xl:text-lg">{blind}% blind</span>
      </span>
      {market > 0 ? (
        <p className="max-w-5xl text-4xl font-extrabold leading-[1.15] tracking-tight text-ink 2xl:text-5xl">
          You never saw{" "}
          <span className="tabular text-sky-600 underline decoration-sky-300 decoration-2 underline-offset-8">{neverSeen.toLocaleString("en-US")}</span> of the{" "}
          <span className="tabular">{market.toLocaleString("en-US")}</span> VC-backed companies in your thesis that raised since 2022.
        </p>
      ) : (
        <p className="text-3xl font-bold tracking-tight text-ink">No VC-backed company in this thesis has raised since 2022 in the data so far.</p>
      )}
      {neverSeen > 0 ? <p className="text-lg text-zinc-600 2xl:text-xl">Worth a look: each one is listed below with its round and source.</p> : null}
    </section>
  );
}

function Stats({ audit }: { audit: Audit }) {
  const s = audit.summary;
  const { blind, captured } = shares(s.never_seen, s.market_companies);
  return (
    <section className="flex flex-col gap-5 rounded-xl border border-slate-200/80 bg-white p-6 shadow-card 2xl:p-8" aria-label="Market and CRM">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3 2xl:gap-6">
        <StatCard label="Thesis market" value={s.market_companies} note="VC-backed companies since 2022" />
        <StatCard
          label="In your CRM"
          value={s.in_crm}
          tone="green"
          note={`${s.invested} invested · ${s.passed} passed · ${s.in_review} in review · ${captured}% captured`}
        />
        <StatCard label="Blind spot" value={s.never_seen} tone="sky" note={`${blind}% unmapped`} />
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-sm font-semibold uppercase tracking-wider text-zinc-600">In CRM vs Never seen</span>
        <div className="flex h-4 w-full overflow-hidden rounded-full bg-slate-200" role="img" aria-label={`In CRM ${captured}%, never seen ${blind}%`}>
          <div className="h-full bg-green-400" style={{ width: `${captured}%` }} />
          <div className="h-full bg-sky-600" style={{ width: `${blind}%` }} />
        </div>
        <div className="tabular flex justify-between gap-4 text-base font-medium">
          <span className="flex items-center gap-2 text-green-700">
            <span className="size-2.5 rounded-full bg-green-400" />
            In CRM {s.in_crm.toLocaleString("en-US")} ({captured}%)
          </span>
          <span className="flex items-center gap-2 text-sky-700">
            Never seen {s.never_seen.toLocaleString("en-US")} ({blind}%)
            <span className="size-2.5 rounded-full bg-sky-600" />
          </span>
        </div>
      </div>
    </section>
  );
}

const TONE = {
  plain: { box: "border-slate-200 bg-slate-50/80", head: "text-zinc-600", num: "text-ink" },
  green: { box: "border-green-200 bg-green-50/60", head: "text-green-700", num: "text-green-700" },
  sky: { box: "border-sky-200 bg-sky-50/60", head: "text-sky-700", num: "text-sky-600" },
};

function StatCard({ label, value, note, tone = "plain" }: { label: string; value: number; note: string; tone?: keyof typeof TONE }) {
  const t = TONE[tone];
  return (
    <div className={`flex flex-col gap-1 rounded-lg border p-5 ${t.box}`}>
      <span className={`text-sm font-semibold uppercase tracking-wider ${t.head}`}>{label}</span>
      <span className={`tabular text-4xl font-bold 2xl:text-5xl ${t.num}`}>{value.toLocaleString("en-US")}</span>
      <span className="text-base text-zinc-700">{note}</span>
    </div>
  );
}

// Stages, then countries, then industries; each group in its own chip colour.
function ThesisChips({ thesis }: { thesis: Audit["thesis"] }) {
  const groups = [
    { items: thesis.stages.map(stageLabel), cls: "border-sky-200 bg-sky-50 text-sky-800" },
    { items: thesis.countries, cls: "border-slate-200 bg-white text-zinc-800" },
    { items: thesis.industries.map((x) => x.name), cls: "border-green-200 bg-green-50 text-green-800" },
  ].filter((g) => g.items.length);
  if (!groups.length) return null;
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="Thesis">
      {groups.flatMap((g, gi) =>
        g.items.map((c, i) => (
          <li key={`${gi}-${c}`} className={`rounded-full border px-3 py-1 text-sm font-medium 2xl:text-base ${g.cls} ${i === 0 && gi > 0 ? "ml-3" : ""}`}>
            {c}
          </li>
        )),
      )}
    </ul>
  );
}

const REGION_ADJ: Record<string, string> = {
  nordics: "Nordic",
  nordic: "Nordic",
  dach: "DACH",
  benelux: "Benelux",
  baltics: "Baltic",
  uk_ireland: "UK & Irish",
  cee: "CEE",
  europe: "European",
};

function regionName(code: string): string {
  return REGION_ADJ[code.toLowerCase()] ?? code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// "Market: 120 Nordic VC-backed companies since 2022 · as of 14 Nov 2026 · data from Cala"
function marketLine(audit: Audit): string {
  const mc = audit.market_coverage;
  const region = mc.region && mc.region_qualifying_companies != null ? mc.region : null;
  const n = (region ? mc.region_qualifying_companies! : mc.qualifying_companies).toLocaleString("en-US");
  const who = region ? `${regionName(region)} VC-backed companies` : "VC-backed companies";
  return `Market: ${n} ${who} since 2022 · as of ${formatDate(mc.as_of, true)} · data from Cala`;
}

/** Small switch between the precomputed demos (GET /api/audit/demos); hidden unless there are at least two. */
function DemoSwitch({ current, onLoaded }: { current: string; onLoaded: (a: Audit) => void }) {
  const [demos, setDemos] = useState<DemoEntry[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getDemos()
      .then((d) => !cancelled && setDemos(d))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (demos.length < 2 || !demos.some((d) => d.fund.id === current)) return null;

  async function pick(id: string) {
    if (id === current || loading) return;
    setLoading(id);
    setFailed(false);
    try {
      onLoaded(await withTimeout(getDemoAudit(id)));
    } catch {
      setFailed(true);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div role="radiogroup" aria-label="Demo fund" className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
        <span className="px-2 text-sm font-medium text-zinc-500">Demo</span>
        {demos.map((d) => {
          const active = d.fund.id === current;
          return (
            <button
              key={d.fund.id}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={!!loading}
              onClick={() => pick(d.fund.id)}
              className={`flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-semibold transition-colors disabled:cursor-wait ${
                active ? "bg-ink text-white" : "text-zinc-700 hover:bg-slate-100"
              }`}
            >
              {loading === d.fund.id ? <Icon name="spinner" className="size-3.5 animate-spin" /> : null}
              {d.fund.name}
            </button>
          );
        })}
      </div>
      {failed ? (
        <span role="alert" className="text-sm text-red-700">
          That demo didn&apos;t load. Try again.
        </span>
      ) : null}
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-6xl animate-pulse flex-col gap-8 px-4 py-10 sm:px-10 2xl:max-w-[1520px]" aria-busy="true" aria-label="Loading">
      <div className="h-10 w-1/3 rounded bg-slate-200" />
      <div className="h-8 w-2/3 rounded bg-slate-200" />
      <div className="h-48 rounded-xl bg-slate-200/70" />
      <div className="h-40 rounded-xl bg-slate-200/70" />
      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 rounded bg-slate-100" />
        ))}
      </div>
    </div>
  );
}
