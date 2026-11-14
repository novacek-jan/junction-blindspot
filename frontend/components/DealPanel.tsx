"use client";

import { useEffect, useState } from "react";
import { ApiError, getDeal } from "@/lib/api";
import type { BlindSpot, DealDetail, DealRound } from "@/lib/types";
import { formatAmount, formatDate, safeUrl, stageLabel, websiteUrl } from "@/lib/format";
import { Icon } from "./Icon";
import { sourceLabel } from "./DealsTable";

/** Side panel for one company: GET /api/deals/{company_id}?fund_id=, every round with its Cala sources. */
export function DealPanel({ row, fundId, onClose }: { row: BlindSpot; fundId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<DealDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDeal(row.company_id, fundId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e instanceof ApiError && e.kind === "not_found" ? "No round details for this company yet." : "Couldn't load the details."));
    return () => {
      cancelled = true;
    };
  }, [row.company_id, fundId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const site = websiteUrl(detail?.website ?? row.website);
  const facts = [detail?.country ?? row.country, detail?.founded ? `Founded ${detail.founded}` : null].filter(Boolean);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${row.name} details`}>
      <div className="animate-fade-in absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="animate-slide-in absolute inset-y-0 right-0 flex w-full max-w-[560px] flex-col border-l border-slate-200 bg-white shadow-[var(--shadow-overlay)] 2xl:max-w-[680px]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 px-7 py-6">
          <div className="flex min-w-0 flex-col gap-2">
            <span className="w-fit rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-xs font-semibold tracking-wide text-sky-700">NOT IN CRM</span>
            <h2 className="text-2xl font-bold tracking-tight text-ink 2xl:text-3xl">{detail?.name ?? row.name}</h2>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-base text-zinc-600">
              {facts.map((f) => (
                <span key={f}>{f}</span>
              ))}
              {site ? (
                <a href={site} target="_blank" rel="noopener noreferrer" className="font-medium text-sky-800 underline underline-offset-2 hover:text-sky-950">
                  {new URL(site).hostname.replace(/^www\./, "")}
                </a>
              ) : null}
            </p>
          </div>
          <button
            type="button"
            autoFocus
            aria-label="Close details"
            onClick={onClose}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-ink"
          >
            <Icon name="close" className="size-5" />
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-7 py-6">
          {detail?.description ? <p className="text-base leading-relaxed text-zinc-700 2xl:text-lg">{detail.description}</p> : null}

          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Funding rounds</h3>
            {detail ? (
              detail.rounds.length ? (
                <ol className="flex flex-col gap-3">
                  {detail.rounds.map((r) => (
                    <RoundCard key={r.id} round={r} />
                  ))}
                </ol>
              ) : (
                <p className="text-base text-zinc-600">Cala lists no rounds for this company.</p>
              )
            ) : error ? (
              <p role="alert" className="text-base text-zinc-700">
                {error}
              </p>
            ) : (
              <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading rounds">
                {[0, 1].map((i) => (
                  <div key={i} className="h-28 animate-pulse rounded-lg bg-slate-100" />
                ))}
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}

function RoundCard({ round: r }: { round: DealRound }) {
  const investors = [...r.lead_investors.map((i) => ({ ...i, lead: true })), ...r.participants.map((i) => ({ ...i, lead: false }))];
  return (
    <li className={`flex flex-col gap-2.5 rounded-lg border p-4 ${r.qualifying ? "border-sky-200 bg-sky-50/40" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-lg font-semibold text-ink">
          {r.label ? stageLabel(r.label) : "Round"}
          <span className="tabular ml-2 font-bold">{formatAmount(r.amount, r.currency ?? "")}</span>
        </span>
        <span className="tabular text-base text-zinc-600">{formatDate(r.date, true)}</span>
      </div>
      {investors.length ? (
        <p className="text-base text-zinc-800">
          {investors.map((i, n) => (
            <span key={`${i.id}-${n}`}>
              {n ? ", " : ""}
              <span className={i.lead ? "font-semibold" : ""}>{i.name}</span>
              {i.lead ? <span className="text-zinc-500"> (lead)</span> : null}
            </span>
          ))}
        </p>
      ) : null}
      {r.sources.length ? (
        <ul className="flex flex-col gap-1">
          {r.sources.map((s, n) => {
            const href = safeUrl(s.url);
            return (
              <li key={`${s.url}-${n}`} className="flex items-center gap-2 text-base">
                <Icon name="link" className="size-3.5 shrink-0 text-zinc-400" />
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="truncate font-medium text-sky-800 underline underline-offset-2 hover:text-sky-950">
                    {s.name}
                  </a>
                ) : (
                  <span className="truncate font-medium">{s.name}</span>
                )}
                <span className="shrink-0 text-zinc-500">{sourceLabel(s)}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500">No source in Cala.</p>
      )}
    </li>
  );
}
