"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell, SimulatedCrmBadge } from "@/components/AppShell";
import { DealsTable } from "@/components/DealsTable";
import { ApiError, ERROR_MESSAGES, getDemoAudit, withTimeout } from "@/lib/api";
import { loadAudit, saveAudit } from "@/lib/auditStore";
import { formatDate, stageLabel } from "@/lib/format";
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

  const { headline, thesis, market_coverage: mc } = audit;
  const n = String(headline.never_seen);

  return (
    <AppShell crumb={audit.fund.name} right={audit.simulated_crm ? <SimulatedCrmBadge /> : null}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-8">
        <div className="flex flex-col gap-3">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-zinc-950 xl:text-5xl">
            {headline.text.startsWith(n) ? (
              <>
                <span className="tabular text-sky-800">{n}</span>
                {headline.text.slice(n.length)}
              </>
            ) : (
              headline.text
            )}
          </h1>
          <ThesisChips thesis={thesis} />
        </div>
        <DealsTable rows={audit.never_seen} />
        <p className="text-sm text-zinc-500">
          Market: {mc.qualifying_companies.toLocaleString("en-US")} {mc.region ? `${mc.region} ` : ""}companies with an investor-backed round since 2022,
          from {mc.european_companies_screened.toLocaleString("en-US")} screened · as of {formatDate(mc.as_of, true)} · data from Cala
        </p>
      </div>
    </AppShell>
  );
}

function ThesisChips({ thesis }: { thesis: Audit["thesis"] }) {
  const chips = [...thesis.stages.map(stageLabel), ...thesis.countries, ...thesis.industries.map((x) => x.name)];
  return (
    <div className="flex flex-col gap-2">
      {chips.length ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Thesis">
          {chips.map((c) => (
            <li key={c} className="rounded-full border border-zinc-300 bg-white px-2.5 py-0.5 text-sm font-medium text-zinc-800">
              {c}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-sm text-zinc-600">Thesis based on {thesis.basis_rounds.toLocaleString("en-US")} rounds</p>
    </div>
  );
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
