"use client";

import { useEffect, useState } from "react";
import { getDeal } from "@/lib/api";
import type { DealDetail, NeverSeenDeal } from "@/lib/types";
import { formatAmount, formatDate, safeUrl, stageLabel, websiteUrl } from "@/lib/format";
import { Icon, type IconName } from "./Icon";
import { SourceIcons, SourceList } from "./Sources";
import { ConflatedFlag } from "./DealsTable";

export function DealPanel({ deal, fundId, onClose }: { deal: NeverSeenDeal; fundId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<DealDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<"idle" | "adding" | "added">("idle");

  useEffect(() => {
    let cancelled = false;
    getDeal(deal.company_id, fundId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Could not load deal."));
    return () => {
      cancelled = true;
    };
  }, [deal.company_id, fundId]);

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

  const rounds = detail ? [...detail.rounds].sort((a, b) => b.date.localeCompare(a.date)) : [];

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${deal.name} deal details`}>
      <div className="animate-fade-in absolute inset-0 bg-black/30 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="animate-slide-in absolute inset-y-0 right-0 flex w-full max-w-[500px] 2xl:max-w-[560px] flex-col border-l border-zinc-200 bg-white shadow-2xl">
        <div className="flex-1 overflow-y-auto px-6 py-6 sm:px-8 sm:py-8">
          <div className="flex flex-col gap-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-sky-600" />
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-sky-600">Missed deal</span>
                <span className="text-zinc-300">·</span>
                <span className="font-mono text-xs text-zinc-500">Never seen</span>
              </div>
              <button
                type="button"
                autoFocus
                aria-label="Close deal details"
                onClick={onClose}
                className="flex size-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-ink"
              >
                <Icon name="close" className="size-[18px]" />
              </button>
            </div>

            {/* Header (available instantly from the table row) */}
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between gap-3">
                <h1 className="text-2xl font-bold tracking-tight text-ink">{deal.name}</h1>
                <span className="tabular shrink-0 font-mono text-xs font-medium text-zinc-500">
                  {stageLabel(deal.stage)} · {formatAmount(deal.amount, deal.currency)}
                </span>
              </div>
              {detail ? (
                <p className="text-sm leading-relaxed text-zinc-600">{detail.description}</p>
              ) : !error ? (
                <div className="h-4 w-4/5 animate-pulse rounded bg-zinc-100" />
              ) : null}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 font-mono text-xs text-zinc-500">
                <span>{deal.country}</span>
                {detail?.founded ? (
                  <>
                    <Dot />
                    <span>Founded {detail.founded}</span>
                  </>
                ) : null}
                <WebsiteLink website={detail?.website ?? deal.website} />
              </div>
            </div>

            <div className="h-px bg-zinc-200" />

            {error ? (
              <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800">
                {error}
              </div>
            ) : !detail ? (
              <PanelSkeleton />
            ) : (
              <>
                {detail.why_missed.length ? (
                  <Section icon="diagnose" title="Why you missed it">
                    <div className="flex flex-col gap-2.5 rounded-r-lg border-l-2 border-sky-600 bg-zinc-50/60 p-3 pl-4">
                      {detail.why_missed.slice(0, 2).map((w, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="select-none pt-px font-mono text-xs font-semibold text-sky-600">{String(i + 1).padStart(2, "0")}</span>
                          <p className="text-sm leading-snug text-ink">{w.reason}</p>
                        </div>
                      ))}
                    </div>
                  </Section>
                ) : null}

                <Section icon="bolt" iconClass="text-green-700" title="Recent news">
                  {detail.recent_news.length ? (
                    <div className="divide-y divide-zinc-200 overflow-hidden rounded-xl border border-zinc-200">
                      {detail.recent_news.map((n, i) => {
                        const href = safeUrl(n.url);
                        const body = (
                          <>
                            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-green-700" />
                            <span className="flex flex-1 flex-col gap-0.5">
                              <span className="text-sm font-medium leading-snug text-ink group-hover:underline">{n.title}</span>
                              <span className="flex items-center gap-2 pt-0.5 font-mono text-xs text-zinc-500">
                                <span>{n.source}</span>
                                <Dot />
                                <span>{formatDate(n.date, true)}</span>
                              </span>
                            </span>
                          </>
                        );
                        return href ? (
                          <a
                            key={`${n.url}-${i}`}
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="group flex items-start gap-3 p-3.5 transition-colors hover:bg-zinc-50"
                          >
                            {body}
                            <Icon name="external" className="mt-1 size-3.5 shrink-0 text-zinc-300 group-hover:text-ink" />
                          </a>
                        ) : (
                          <div key={`${n.url}-${i}`} className="flex items-start gap-3 p-3.5">
                            {body}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-500">No recent news found.</p>
                  )}
                </Section>

                <Section icon="bank" title="Round timeline">
                  <ol className="ml-2 flex flex-col gap-5 border-l border-zinc-200 py-1 pl-5">
                    {rounds.map((r, i) => (
                      <li key={`${r.label}-${r.date}`} className="relative flex flex-col gap-1">
                        <span className={`absolute -left-[25px] top-1.5 size-2 rounded-full ring-4 ring-white ${i === 0 ? "bg-ink" : "bg-zinc-400"}`} />
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                            {stageLabel(r.label)} · <span className="tabular">{formatAmount(r.amount, r.currency)}</span>
                            {r.conflated ? <ConflatedFlag /> : null}
                          </span>
                          <span className="flex items-center gap-2">
                            <SourceIcons sources={r.sources} />
                            <span className="tabular font-mono text-xs text-zinc-500">{formatDate(r.date)}</span>
                          </span>
                        </div>
                        <span className="text-xs text-zinc-500">
                          Lead:{" "}
                          <strong className="font-medium text-ink">
                            {r.lead_investors.length ? r.lead_investors.map((l) => l.name).join(", ") : "undisclosed"}
                          </strong>
                          {r.participants.length ? <> · With: {r.participants.map((p) => p.name).join(", ")}</> : null}
                        </span>
                      </li>
                    ))}
                  </ol>
                </Section>

                <SourceList sources={detail.sources} />
              </>
            )}
          </div>
        </div>

        <div className="border-t border-zinc-200 bg-white p-5 sm:p-6">
          <button
            type="button"
            disabled={added !== "idle"}
            onClick={() => {
              // No-op for now: there is no pipeline write endpoint in the contract.
              setAdded("adding");
              setTimeout(() => setAdded("added"), 500);
            }}
            className={`flex h-11 w-full items-center justify-center gap-2 rounded-lg text-sm font-medium text-white shadow-sm transition-all active:scale-[0.99] ${
              added === "added" ? "bg-green-700" : "bg-ink hover:bg-zinc-800"
            }`}
          >
            <Icon name={added === "added" ? "check" : added === "adding" ? "spinner" : "add"} className={`size-[18px] ${added === "adding" ? "animate-spin" : ""}`} />
            {added === "added" ? "Added to pipeline" : added === "adding" ? "Adding…" : "Add to pipeline"}
          </button>
        </div>
      </aside>
    </div>
  );
}

function Section({ icon, iconClass = "text-zinc-500", title, children }: { icon: IconName; iconClass?: string; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Icon name={icon} className={`size-4 ${iconClass}`} />
        <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function WebsiteLink({ website }: { website: string }) {
  const href = websiteUrl(website);
  if (!website) return null;
  return (
    <>
      <Dot />
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-sky-600 hover:underline">
          {website}
          <Icon name="external" className="size-3" />
        </a>
      ) : (
        <span>{website}</span>
      )}
    </>
  );
}

function Dot() {
  return <span className="text-zinc-300">·</span>;
}

function PanelSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-6" aria-label="Loading deal">
      {[3, 2, 2].map((n, i) => (
        <div key={i} className="flex flex-col gap-2">
          <div className="h-3 w-32 rounded bg-zinc-100" />
          {Array.from({ length: n }).map((_, j) => (
            <div key={j} className="h-10 rounded-lg bg-zinc-50" />
          ))}
        </div>
      ))}
    </div>
  );
}
