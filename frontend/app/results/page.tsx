"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell, SimulatedCrmBadge } from "@/components/AppShell";
import { DealsTable } from "@/components/DealsTable";
import { ApiError, ERROR_MESSAGES, getDemoAudit, withTimeout } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import { stageLabel } from "@/lib/format";
import type { Audit } from "@/lib/types";

export default function ResultsPage() {
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Audit handed over from "/"; on a direct visit load the demo audit.
    let cancelled = false;
    const stored = loadAudit();
    (stored ? Promise.resolve(stored) : withTimeout(getDemoAudit()))
      .then((a) => {
        if (cancelled) return;
        saveAudit(a);
        setAudit(a);
      })
      .catch((e) => {
        if (cancelled) return;
        // The demo itself failed here, so don't suggest trying it.
        const kind = e instanceof ApiError ? e.kind : "other";
        setError(kind === "timeout" ? "No response after 15 seconds." : kind === "unavailable" || kind === "live_off" ? "Backend unavailable." : ERROR_MESSAGES[kind]);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (error) {
    return (
      <AppShell crumb="Results">
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
          <p role="alert" className="text-lg font-semibold text-zinc-950">
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
            <Link href="/" className="flex h-11 items-center rounded-lg border border-zinc-300 bg-white px-5 text-base font-semibold hover:bg-zinc-50">
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

  const count = audit.summary?.never_seen ?? audit.never_seen_deals.length;
  const thesis = thesisLine(audit);

  return (
    <AppShell crumb={audit.fund.name} right={audit.simulated_crm ? <SimulatedCrmBadge /> : null}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-8">
        <div className="flex flex-col gap-3">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-zinc-950 xl:text-5xl">
            <span className="tabular text-sky-800">{count}</span> companies in your thesis raised since 2022 and never hit your CRM
          </h1>
          {thesis ? <p className="text-lg font-medium text-zinc-800">{thesis}</p> : null}
        </div>
        <DealsTable deals={audit.never_seen_deals} />
        <p className="text-sm text-zinc-500">Market data from Cala · every row links to its source</p>
      </div>
    </AppShell>
  );
}

// "Thesis: Seed, Series A · Germany, France · Fintech". Prefers audit.thesis, falls back to the heatmap axes.
function thesisLine(audit: Audit): string | null {
  const stages = audit.thesis?.stages ?? audit.heatmap?.stages ?? [];
  const countries = audit.thesis?.countries ?? audit.heatmap?.countries ?? [];
  const sectors = audit.thesis?.sectors ?? [];
  const parts = [stages.map(stageLabel).join(", "), countries.join(", "), sectors.join(", ")].filter(Boolean);
  return parts.length ? `Thesis: ${parts.join(" · ")}` : null;
}

function ResultsSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-7xl animate-pulse flex-col gap-6 px-4 py-6 sm:px-8" aria-busy="true" aria-label="Loading">
      <div className="h-12 w-3/4 rounded bg-zinc-200" />
      <div className="h-6 w-1/2 rounded bg-zinc-200" />
      <div className="flex flex-col gap-2 rounded-xl border border-zinc-200 bg-white p-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-9 rounded bg-zinc-100" />
        ))}
      </div>
    </div>
  );
}
