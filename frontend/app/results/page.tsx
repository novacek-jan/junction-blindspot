"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell, CalaBadge, SimulatedCrmBadge } from "@/components/AppShell";
import { Venn } from "@/components/Venn";
import { Heatmap } from "@/components/Heatmap";
import { BlindSpots } from "@/components/BlindSpots";
import { DealsTable } from "@/components/DealsTable";
import { DealPanel } from "@/components/DealPanel";
import { Icon } from "@/components/Icon";
import { ApiError, getDemoAudit } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import type { Audit, NeverSeenDeal } from "@/lib/types";

export default function ResultsPage() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<NeverSeenDeal | null>(null);
  const [hasOpened, setHasOpened] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const close = useCallback(() => setOpen(null), []);
  const openDeal = useCallback((d: NeverSeenDeal) => {
    setOpen(d);
    setHasOpened(true);
  }, []);

  useEffect(() => {
    // Audit handed over from "/"; on a direct visit (or "Try the demo") load the demo audit.
    let cancelled = false;
    const stored = loadAudit();
    (stored ? Promise.resolve(stored) : getDemoAudit())
      .then((a) => {
        if (cancelled) return;
        saveAudit(a);
        setAudit(a);
      })
      .catch((e) => {
        if (cancelled) return;
        // The demo itself failed here, so don't suggest "try the demo".
        setError(e instanceof ApiError && e.kind === "unavailable" ? "Backend unavailable. Please try again in a moment." : e instanceof Error ? e.message : "Could not load the audit.");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (error) {
    return (
      <AppShell crumb="Results">
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-700">
            <Icon name="warning" className="size-5" />
          </span>
          <h1 className="text-lg font-semibold">We couldn&apos;t load this audit</h1>
          <p role="alert" className="text-sm text-zinc-600">
            {error}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
              className="h-10 rounded-lg bg-ink px-4 text-sm font-medium text-white hover:bg-ink-hover"
            >
              Try again
            </button>
            <Link href="/" className="flex h-10 items-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium hover:bg-slate-50">
              Back to start
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  if (!audit) {
    return (
      <AppShell crumb="Loading audit…">
        <ResultsSkeleton />
      </AppShell>
    );
  }

  const { summary } = audit;
  const missedPct = Math.round(100 - summary.coverage_pct);
  const noBlindSpots = summary.never_seen === 0 && audit.never_seen_deals.length === 0;

  return (
    <AppShell
      crumb={`${audit.fund.name} vs. ${audit.peers.length} peers`}
      right={
        <>
          {audit.simulated_crm ? <SimulatedCrmBadge /> : null}
          <span className="hidden sm:inline-flex">
            <CalaBadge />
          </span>
        </>
      }
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-6 sm:px-8 lg:px-10 lg:py-8 2xl:max-w-7xl">
        {/* Hero: headline + Venn must sit above the fold at 1440×900 */}
        <section className="flex flex-col gap-8 rounded-xl border border-slate-200/80 bg-white p-6 shadow-[var(--shadow-card)] sm:p-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex max-w-2xl flex-1 flex-col 2xl:max-w-3xl">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1">
              <span className="size-1.5 animate-pulse rounded-full bg-sky-600" />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-600">Coverage gap audit</span>
              <span className="tabular border-l border-sky-200 pl-2 font-mono text-[11px] text-zinc-600">{missedPct}% blind</span>
            </div>
            {noBlindSpots ? (
              <h1 className="text-3xl font-extrabold leading-[1.15] tracking-tight text-ink lg:text-4xl 2xl:text-5xl">
                You saw all <span className="tabular font-mono text-green-700">{summary.market_deals}</span> deals your peers closed.
              </h1>
            ) : (
              <h1 className="text-3xl font-extrabold leading-[1.15] tracking-tight text-ink lg:text-4xl 2xl:text-5xl">
                You never saw{" "}
                <span className="tabular font-mono text-sky-600 underline decoration-sky-300 decoration-2 underline-offset-8">{summary.never_seen}</span>{" "}
                of the <span className="tabular font-mono">{summary.market_deals}</span> deals your peers closed.
              </h1>
            )}
            <p className="mt-4 text-sm leading-relaxed text-zinc-600 2xl:text-base">
              {summary.in_pipeline} reached your pipeline: {summary.invested} invested, {summary.passed} passed, {summary.in_review} in review.
              Peers: {audit.peers.map((p) => p.name).join(", ")}.
            </p>
            <div className="mt-6 flex flex-col gap-1.5">
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div className="h-full bg-green-400" style={{ width: `${summary.coverage_pct}%` }} />
                <div className="h-full bg-sky-600" style={{ width: `${100 - summary.coverage_pct}%` }} />
              </div>
              <div className="flex justify-between font-mono text-[11px]">
                <span className="font-medium text-green-700">Seen {summary.coverage_pct.toFixed(0)}%</span>
                <span className="font-semibold text-sky-700">Never seen {missedPct}%</span>
              </div>
            </div>
          </div>
          <div className="w-full shrink-0 rounded-xl border border-slate-200/80 bg-slate-50/80 p-4 lg:w-[340px] 2xl:w-[400px]">
            <Venn venn={audit.venn} />
          </div>
        </section>

        <div className="grid grid-cols-1 items-start gap-8 md:grid-cols-2">
          <Heatmap heatmap={audit.heatmap} />
          <BlindSpots audit={audit} />
        </div>

        <DealsTable
          deals={audit.never_seen_deals}
          total={summary.never_seen}
          selectedId={open?.company_id}
          highlightFirst={!hasOpened}
          onOpen={openDeal}
        />
      </div>

      {open ? <DealPanel key={open.company_id} deal={open} fundId={audit.fund.id} onClose={close} /> : null}
    </AppShell>
  );
}

function ResultsSkeleton() {
  const bar = "rounded bg-slate-200/80";
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-6 sm:px-8 lg:px-10 lg:py-8 2xl:max-w-7xl" aria-busy="true" aria-label="Loading audit">
      <section className="flex animate-pulse flex-col gap-8 rounded-xl border border-slate-200/80 bg-white p-6 sm:p-8 lg:flex-row lg:items-center">
        <div className="flex flex-1 flex-col gap-4">
          <div className={`h-6 w-48 ${bar}`} />
          <div className={`h-9 w-full max-w-xl ${bar}`} />
          <div className={`h-9 w-3/4 max-w-md ${bar}`} />
          <div className={`h-4 w-2/3 ${bar}`} />
          <div className={`mt-2 h-2 w-full rounded-full ${bar}`} />
        </div>
        <div className="flex h-56 w-full shrink-0 items-center justify-center gap-0 rounded-xl bg-slate-50 lg:w-[340px] 2xl:w-[400px]">
          <div className="size-36 rounded-full bg-slate-200/70" />
          <div className="-ml-12 size-32 rounded-full bg-slate-200/50" />
        </div>
      </section>
      <div className="grid animate-pulse grid-cols-1 gap-8 md:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i} className="flex flex-col gap-3 rounded-xl border border-slate-200/80 bg-white p-6">
            <div className={`h-4 w-40 ${bar}`} />
            {Array.from({ length: 5 }).map((_, j) => (
              <div key={j} className={`h-8 ${bar} opacity-60`} />
            ))}
          </div>
        ))}
      </div>
      <div className="flex animate-pulse flex-col gap-2 rounded-xl border border-slate-200/80 bg-white p-5">
        <div className={`mb-2 h-4 w-48 ${bar}`} />
        {Array.from({ length: 6 }).map((_, j) => (
          <div key={j} className={`h-10 ${bar} opacity-50`} />
        ))}
      </div>
      <p className="sr-only">Loading audit…</p>
    </div>
  );
}
