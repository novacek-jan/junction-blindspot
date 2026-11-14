"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell, CalaBadge, SimulatedCrmBadge } from "@/components/AppShell";
import { Venn } from "@/components/Venn";
import { Heatmap } from "@/components/Heatmap";
import { BlindSpots } from "@/components/BlindSpots";
import { DealsTable } from "@/components/DealsTable";
import { DealPanel } from "@/components/DealPanel";
import { getDemoAudit } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import type { Audit, NeverSeenDeal } from "@/lib/types";

export default function ResultsPage() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<NeverSeenDeal | null>(null);
  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    // Audit handed over from "/"; on a direct visit fall back to the demo audit.
    const stored = loadAudit();
    (stored ? Promise.resolve(stored) : getDemoAudit())
      .then((a) => {
        saveAudit(a);
        setAudit(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load audit."));
  }, []);

  if (error) {
    return (
      <AppShell crumb="Results">
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
          <p className="text-sm text-red-700">{error}</p>
          <Link href="/" className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white">
            Start a new audit
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!audit) {
    return (
      <AppShell crumb="Results">
        <div className="mx-auto flex w-full max-w-6xl animate-pulse flex-col gap-8 px-4 py-10 sm:px-10">
          <div className="h-56 rounded-xl bg-white" />
          <div className="grid gap-8 md:grid-cols-2">
            <div className="h-72 rounded-xl bg-white" />
            <div className="h-72 rounded-xl bg-white" />
          </div>
        </div>
      </AppShell>
    );
  }

  const { summary } = audit;
  const missedPct = Math.round(100 - summary.coverage_pct);

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
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8 sm:px-8 lg:px-10 lg:py-10">
        {/* Hero */}
        <section className="flex flex-col gap-8 rounded-xl border border-slate-200/80 bg-white p-6 shadow-[var(--shadow-card)] sm:p-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex max-w-2xl flex-1 flex-col">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1">
              <span className="size-1.5 animate-pulse rounded-full bg-sky-600" />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-600">Coverage gap audit</span>
              <span className="tabular border-l border-sky-200 pl-2 font-mono text-[11px] text-zinc-600">{missedPct}% blind</span>
            </div>
            <h1 className="text-3xl font-extrabold leading-[1.15] tracking-tight text-ink lg:text-4xl">
              You never saw{" "}
              <span className="tabular font-mono text-sky-600 underline decoration-sky-300 decoration-2 underline-offset-8">{summary.never_seen}</span>{" "}
              of the <span className="tabular font-mono">{summary.market_deals}</span> deals your peers closed.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-zinc-600">
              {summary.in_pipeline} reached your pipeline — {summary.invested} invested, {summary.passed} passed, {summary.in_review} in review.
              Peers: {audit.peers.map((p) => p.name).join(", ")}.
            </p>
            <div className="mt-6 flex flex-col gap-1.5">
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div className="h-full bg-green-400" style={{ width: `${summary.coverage_pct}%` }} />
                <div className="h-full bg-sky-600" style={{ width: `${100 - summary.coverage_pct}%` }} />
              </div>
              <div className="flex justify-between font-mono text-[10px]">
                <span className="font-medium text-green-700">Seen {summary.coverage_pct.toFixed(0)}%</span>
                <span className="font-semibold text-sky-700">Never seen {missedPct}%</span>
              </div>
            </div>
          </div>
          <div className="w-full shrink-0 rounded-xl border border-slate-200/80 bg-slate-50/80 p-4 lg:w-[340px]">
            <Venn venn={audit.venn} />
          </div>
        </section>

        <div className="grid grid-cols-1 items-start gap-8 md:grid-cols-2">
          <Heatmap heatmap={audit.heatmap} />
          <BlindSpots audit={audit} />
        </div>

        <DealsTable deals={audit.never_seen_deals} total={summary.never_seen} selectedId={open?.company_id} onOpen={setOpen} />
      </div>

      {open ? <DealPanel key={open.company_id} deal={open} fundId={audit.fund.id} onClose={close} /> : null}
    </AppShell>
  );
}
