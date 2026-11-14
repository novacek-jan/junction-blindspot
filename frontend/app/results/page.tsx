"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Briefing } from "@/components/Briefing";
import { Chip } from "@/components/Chip";
import { DealPanel } from "@/components/DealPanel";
import { DealsTable } from "@/components/DealsTable";
import { DotField } from "@/components/DotField";
import { ApiError, ERROR_MESSAGES, getDemoAudit, getDemos, withTimeout } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import { industryWeights, longDate, regionLabel, sectorLabel, stageRange } from "@/lib/present";
import type { Audit, BlindSpot } from "@/lib/types";

/**
 * /results shows the audit handed over from "/" (session storage) or, on a direct visit, the default demo.
 * ?demo=earlybird picks another precomputed demo by fund name (there is no visible switch).
 */
async function loadForUrl(): Promise<Audit> {
  const wanted = new URLSearchParams(window.location.search).get("demo");
  if (wanted != null) {
    const key = slug(wanted);
    const demos = key ? await withTimeout(getDemos()).catch(() => []) : [];
    const match = demos.find((d) => slug(d.fund.name).startsWith(key)) ?? demos.find((d) => slug(d.fund.name).includes(key));
    return withTimeout(getDemoAudit(match?.fund.id));
  }
  return loadAudit() ?? withTimeout(getDemoAudit());
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export default function ResultsPage() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<BlindSpot | null>(null);
  const closePanel = useCallback(() => setOpen(null), []);

  useEffect(() => {
    let cancelled = false;
    loadForUrl()
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
  const sectors = sectorLabel(t.industries, 4, industryWeights(audit.never_seen.map((r) => r.industries)));
  const insights = audit.briefing?.insights ?? [];

  return (
    <AppShell active="audits">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-12 px-5 pb-[72px] pt-4 sm:px-10 sm:pt-6 2xl:max-w-[1480px] 2xl:gap-14">
        <section className="flex flex-wrap items-center gap-10 sm:gap-12">
          <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-6">
            <span className="text-[15px] font-semibold text-muted 2xl:text-base">
              {audit.fund.name} · audit of {longDate(audit.period?.to ?? audit.market_coverage.as_of)}
            </span>
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
          </div>
          <DotField summary={audit.summary} />
        </section>

        {audit.briefing && insights.length ? <Briefing briefing={audit.briefing} rows={audit.never_seen} onOpen={setOpen} /> : null}

        <DealsTable rows={audit.never_seen} onOpen={setOpen} />

        <p className="m-0 text-center text-sm text-faint 2xl:text-base">{marketSentence(audit)}</p>
      </div>
      {open ? <DealPanel key={open.company_id} row={open} fundId={audit.fund.id} onClose={closePanel} /> : null}
    </AppShell>
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

function ResultsSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[1240px] animate-pulse flex-col gap-12 px-5 pb-16 pt-6 sm:px-10 2xl:max-w-[1480px]" aria-busy="true" aria-label="Loading audit">
      <div className="flex flex-wrap gap-12">
        <div className="flex flex-[1_1_520px] flex-col gap-5">
          <div className="h-4 w-64 rounded bg-line" />
          <div className="h-14 w-full rounded-lg bg-line" />
          <div className="h-14 w-4/5 rounded-lg bg-line" />
          <div className="h-8 w-2/3 rounded-full bg-line" />
        </div>
        <div className="h-72 flex-[1_1_420px] rounded-3xl bg-line/70" />
      </div>
      <div className="h-64 rounded-3xl bg-line/60" />
      <div className="h-96 rounded-3xl bg-line/50" />
    </div>
  );
}
