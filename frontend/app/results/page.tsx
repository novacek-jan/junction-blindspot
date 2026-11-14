"use client";

import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Briefing } from "@/components/Briefing";
import { Chip } from "@/components/Chip";
import { DealPanel } from "@/components/DealPanel";
import { DealsTable } from "@/components/DealsTable";
import { DotField } from "@/components/DotField";
import { ResultsSkeleton } from "@/components/ResultsSkeleton";
import { ApiError, ERROR_MESSAGES, getDemoAudit, getDemos, withTimeout } from "@/lib/api";
import { loadUploadedAudit } from "@/lib/auditStore";
import { liveUpdatedIds, longDate, regionLabel, sectorLabel, stageRange } from "@/lib/present";
import type { Audit, BlindSpot, LiveCheck } from "@/lib/types";

/**
 * /results ("Audits") shows the audit run in this tab (session storage, flagged `fromUpload`), else an empty state.
 * ?demo=lifeline / ?demo=earlybird is an unlinked backup URL: that precomputed demo, picked by fund name and always
 * fetched fresh and never stored (it leaves the tab's own audit untouched).
 */
async function loadForUrl(): Promise<Audit | null> {
  const wanted = new URLSearchParams(window.location.search).get("demo");
  if (wanted != null) {
    const key = slug(wanted);
    const demos = key ? await withTimeout(getDemos()).catch(() => []) : [];
    const match = demos.find((d) => slug(d.fund.name).startsWith(key)) ?? demos.find((d) => slug(d.fund.name).includes(key));
    return withTimeout(getDemoAudit(match?.fund.id));
  }
  return loadUploadedAudit();
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/**
 * Next hides pages with React <Activity> (cacheComponents), so the view is remounted under a new key whenever
 * /results is hidden: each visit reads the tab's latest audit again (skeleton first, never the previous audit).
 */
export default function ResultsPage() {
  const [visit, setVisit] = useState(0);
  useLayoutEffect(() => () => setVisit((v) => v + 1), []);
  return <ResultsView key={visit} />;
}

function ResultsView() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<BlindSpot | null>(null);
  const closePanel = useCallback(() => setOpen(null), []);

  useEffect(() => {
    let cancelled = false;
    loadForUrl()
      .then((a) => {
        if (cancelled) return;
        setAudit(a);
        setEmpty(!a);
      })
      .catch((e) => !cancelled && setError(loadError(e)));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (error) {
    return (
      <AppShell active="audits">
        <div className="mx-auto flex max-w-md flex-col items-center gap-5 px-5 py-24 text-center">
          <p role="alert" className="font-display text-2xl font-semibold text-ink">
            {error}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
              className="h-11 rounded-full bg-ink px-5 text-[15px] font-semibold text-white hover:bg-ink-hover"
            >
              Retry
            </button>
            <Link href="/" className="flex h-11 items-center rounded-full border border-line bg-white px-5 text-[15px] font-semibold text-ink no-underline hover:bg-chip">
              New audit
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  if (empty) {
    return (
      <AppShell active="audits">
        <EmptyState />
      </AppShell>
    );
  }

  if (!audit) {
    return (
      <AppShell active="audits">
        <ResultsSkeleton />
      </AppShell>
    );
  }

  const n = audit.headline?.never_seen ?? audit.summary.never_seen;
  const t = audit.thesis;
  const stages = stageRange(t.stages);
  const region = regionLabel(t.countries);
  const sectors = sectorLabel(t.industries, 3);
  const insights = audit.briefing?.insights ?? [];

  return (
    <AppShell active="audits">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-12 px-5 pb-[72px] pt-4 sm:px-10 sm:pt-6 2xl:max-w-[1480px] 2xl:gap-14">
        <section className="flex flex-wrap items-center gap-10 sm:gap-12">
          <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[15px] font-semibold text-muted 2xl:text-base">
                {audit.fund.name} · audit of {longDate(audit.period?.to ?? audit.market_coverage.as_of)}
              </span>
              <Link
                href="/"
                className="inline-flex h-10 items-center gap-2 rounded-full border border-line bg-white px-4 text-[15px] font-semibold text-ink no-underline transition-colors hover:bg-chip"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New audit
              </Link>
            </div>
            <h1 className="m-0 font-display text-[38px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[58px] 2xl:text-[66px]">
              <span className="marker">
                {n.toLocaleString("en-US")} {n === 1 ? "company" : "companies"}
              </span>{" "}
              in your thesis raised since 2022 and never hit your CRM.
            </h1>
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-[15px] text-muted 2xl:text-base">
                Thesis from {t.basis_rounds.toLocaleString("en-US")} own {t.basis_rounds === 1 ? "round" : "rounds"}
              </span>
              {stages ? (
                <Chip tone="sky" size="lg">
                  {stages}
                </Chip>
              ) : null}
              {region ? (
                <Chip tone="mint" size="lg">
                  {region}
                </Chip>
              ) : null}
              {sectors ? (
                <Chip tone="plain" size="lg">
                  {sectors}
                </Chip>
              ) : null}
            </div>
            {audit.live_check ? <LiveLine check={audit.live_check} /> : null}
          </div>
          <DotField summary={audit.summary} />
        </section>

        {audit.briefing && insights.length ? <Briefing briefing={audit.briefing} rows={audit.never_seen} onOpen={setOpen} /> : null}

        <DealsTable rows={audit.never_seen} onOpen={setOpen} updated={liveUpdatedIds(audit)} />

        <p className="m-0 text-center text-sm text-faint 2xl:text-base">{marketSentence(audit)}</p>
      </div>
      {open ? <DealPanel key={open.company_id} row={open} fundId={audit.fund.id} onClose={closePanel} /> : null}
    </AppShell>
  );
}

// "Rounds re-checked live with Cala · 2 new rounds found" (partial / offline variants), with a status dot.
function LiveLine({ check }: { check: LiveCheck }) {
  const n = (x: number | null | undefined) => (typeof x === "number" && Number.isFinite(x) ? x : null);
  const updated = n(check.updated) ?? 0;
  const ok = check.status === "ok";
  const partial = check.status === "partial";
  const parts = [ok ? "Rounds re-checked live with Cala" : partial ? "Partly re-checked with Cala" : "Using stored Cala data"];
  if (updated > 0) parts.push(`${updated.toLocaleString("en-US")} new ${updated === 1 ? "round" : "rounds"} found`);
  const dot = ok ? "bg-mint-dot" : partial ? "bg-agg-ink/60" : "bg-field";
  return (
    <p className="m-0 flex items-center gap-2 text-sm text-muted 2xl:text-[15px]" role="status">
      <span className="relative flex size-2.5 shrink-0" aria-hidden="true">
        {ok ? <span className="absolute inset-0 animate-ping rounded-full bg-mint-dot opacity-60 motion-reduce:hidden" /> : null}
        <span className={`relative size-2.5 rounded-full ${dot}`} />
      </span>
      {parts.filter(Boolean).join(" · ")}
    </p>
  );
}

function loadError(e: unknown): string {
  const kind = e instanceof ApiError ? e.kind : "other";
  return kind === "timeout" ? "No response after 15 seconds." : kind === "unavailable" || kind === "live_off" ? "Backend unavailable." : ERROR_MESSAGES[kind];
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

// "Market built from Cala: 46 Nordic VC-backed companies since 2022, from 1,915 European companies screened. Updated 14 Nov 2026."
function marketSentence(audit: Audit): string {
  const mc = audit.market_coverage;
  const region = mc.region && mc.region_qualifying_companies != null ? mc.region : null;
  const count = (region ? mc.region_qualifying_companies! : mc.qualifying_companies).toLocaleString("en-US");
  const adj = region ? `${REGION_ADJ[region.toLowerCase()] ?? region.replace(/_/g, " ")} ` : "";
  return `Market built from Cala: ${count} ${adj}VC-backed companies since 2022, from ${mc.european_companies_screened.toLocaleString("en-US")} European companies screened. Updated ${longDate(mc.as_of)}.`;
}

// Empty state in the design's style: soft dot field, big display heading, one line, ink pill button back to "/".
function EmptyState() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-6 px-5 pb-24 pt-16 text-center sm:pt-24">
      <div className="grid grid-cols-6 gap-2" aria-hidden="true">
        {Array.from({ length: 18 }, (_, i) => (
          <span key={i} className={`size-3.5 rounded-full ${i % 7 === 3 ? "bg-sky-mid" : i % 5 === 1 ? "bg-mint-mid" : "bg-line"}`} />
        ))}
      </div>
      <h1 className="m-0 font-display text-[40px] font-bold leading-[1.05] tracking-[-0.04em] sm:text-[52px]">No audits yet</h1>
      <p className="m-0 max-w-md text-[17px] leading-normal text-body">
        Pick your fund and upload a CRM export to see which companies in your thesis never reached your pipeline.
      </p>
      <Link
        href="/"
        className="mt-2 inline-flex h-14 items-center gap-2.5 rounded-[14px] bg-ink px-7 font-display text-lg font-semibold text-white no-underline transition-colors hover:bg-ink-hover"
      >
        Run your first audit
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      </Link>
    </div>
  );
}

