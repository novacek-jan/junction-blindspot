"use client";

import { useEffect, useState } from "react";
import { ApiError, getDeal } from "@/lib/api";
import type { BlindSpot, DealDetail, DealRound, OrgRef } from "@/lib/types";
import { formatAmount, formatDate, hostOf, safeUrl, stageLabel, websiteUrl } from "@/lib/format";
import { monogram, sourceChip } from "@/lib/present";

const SINCE = "2022-01-01";
const NOT_EQUITY = new Set(["GRANT", "DEBT_FINANCING", "VENTURE_DEBT", "LOAN"]);
const MAX_NEWS = 5;

/**
 * Side panel (design/claude/DealPanel): why it fits, rounds since 2022 as a timeline, sources per round,
 * then "Latest news from Cala" (up to 5 items from recent_news; skeleton while loading, hidden when empty).
 */
export function DealPanel({ row, fundId, onClose }: { row: BlindSpot; fundId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<DealDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDeal(row.company_id, fundId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e instanceof ApiError && e.kind === "not_found" ? "No round details for this company yet." : "Couldn't load the rounds."));
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
  const country = detail?.country ?? row.country;
  const rounds = (detail?.rounds ?? []).filter((r) => r.id === row.round.id || (r.date != null && r.date >= SINCE));

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${row.name} details`}>
      <div className="animate-fade-in absolute inset-0 bg-ink/30" onClick={onClose} />
      <aside className="animate-slide-in absolute inset-y-0 right-0 flex w-full max-w-[560px] flex-col overflow-hidden bg-white shadow-[var(--shadow-panel)] sm:rounded-l-3xl 2xl:max-w-[640px]">
        <div className="flex flex-col gap-4 px-6 pb-6 pt-7 sm:px-8">
          <div className="flex items-center justify-between">
            <span className="inline-flex h-[30px] items-center gap-2 rounded-full bg-sky-wash px-3 text-[13px] font-semibold text-sky-ink">
              <span className="size-2 rounded-full bg-sky-dot" />
              Never in your CRM
            </span>
            <button
              type="button"
              autoFocus
              aria-label="Close"
              onClick={onClose}
              className="flex size-11 items-center justify-center rounded-full bg-chip text-muted transition-colors hover:bg-line hover:text-ink"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          <div className="flex items-center gap-4">
            <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-sky-wash font-display text-2xl font-bold text-sky-ink">{monogram(row.name)}</span>
            <div className="flex min-w-0 flex-col gap-1">
              <h2 className="m-0 font-display text-[28px] font-bold leading-tight tracking-[-0.03em] sm:text-[32px]">{detail?.name ?? row.name}</h2>
              <span className="text-[15px] text-muted">
                {[country, detail?.founded ? `founded ${detail.founded}` : null].filter(Boolean).join(" · ")}
                {site ? (
                  <>
                    {country || detail?.founded ? " · " : ""}
                    <a href={site} target="_blank" rel="noopener noreferrer" className="font-semibold text-link hover:text-sky-ink">
                      {new URL(site).hostname.replace(/^www\./, "")}
                    </a>
                  </>
                ) : null}
              </span>
            </div>
          </div>
          {detail?.description ? <p className="m-0 text-[15px] leading-relaxed text-muted 2xl:text-base">{detail.description}</p> : null}
        </div>

        <div className="mx-6 flex flex-col gap-1 rounded-2xl bg-mint-wash px-5 py-[18px] sm:mx-8">
          <span className="text-[13px] font-semibold text-mint-ink">Why it fits your thesis</span>
          <span className="text-[15px] leading-normal text-ink 2xl:text-base">{whyItFits(row)}</span>
        </div>

        <div className="flex flex-1 flex-col overflow-y-auto px-6 py-7 sm:px-8">
          <h3 className="m-0 mb-4 font-display text-xl font-semibold">Rounds since 2022</h3>
          {detail ? (
            rounds.length ? (
              <ol className="m-0 list-none p-0">
                {rounds.map((r, i) => (
                  <RoundItem key={r.id} round={r} thesis={r.id === row.round.id} last={i === rounds.length - 1} />
                ))}
              </ol>
            ) : (
              <p className="text-[15px] text-muted">Cala lists no rounds since 2022 for this company.</p>
            )
          ) : error ? (
            <p role="alert" className="text-[15px] text-ink">
              {error}
            </p>
          ) : (
            <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading rounds">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-20 animate-pulse rounded-2xl bg-chip" />
              ))}
            </div>
          )}
          {error ? null : <News items={detail ? detail.recent_news : undefined} />}
        </div>
      </aside>
    </div>
  );
}

// "Series A in Finland in Nov 2023, backed by Voima Ventures and Earth VC."
function whyItFits(row: BlindSpot): string {
  const r = row.round;
  const parts = [r.label ? stageLabel(r.label) : "A round", row.country ? `in ${row.country}` : null, r.date ? `in ${formatDate(r.date)}` : null].filter(Boolean).join(" ");
  const vcs = (r.investors ?? []).filter((i) => i.is_vc ?? i.type !== "Person");
  const sorted = [...vcs.filter((i) => i.is_lead), ...vcs.filter((i) => !i.is_lead)].map((i) => i.name);
  if (!sorted.length) return `${parts}.`;
  const who = sorted.length > 2 ? `${sorted.slice(0, 2).join(", ")} and ${sorted.length - 2} more` : sorted.join(" and ");
  return `${parts}, backed by ${who}.`;
}

function names(list: OrgRef[]): string {
  const n = list.map((x) => x.name);
  return n.length <= 1 ? n.join("") : `${n.slice(0, -1).join(", ")} and ${n[n.length - 1]}`;
}

// "Led by A and B, with C" / "With A, B" / why a round is not counted.
function investorLine(r: DealRound): string | null {
  const lead = r.lead_investors ?? [];
  const rest = r.participants ?? [];
  if (lead.length) return `Led by ${names(lead)}${rest.length ? `, with ${names(rest)}` : ""}`;
  if (rest.length) return `With ${names(rest)}`;
  return null;
}

function notCountedReason(r: DealRound): string {
  if (r.label && NOT_EQUITY.has(r.label)) return "Grant or loan, not counted";
  if (!(r.lead_investors?.length || r.participants?.length)) return "No named investor, not counted";
  return "No VC among the investors, not counted";
}

function RoundItem({ round: r, thesis, last }: { round: DealRound; thesis: boolean; last: boolean }) {
  const counted = thesis || r.qualifying !== false;
  const dot = thesis
    ? "bg-sky-dot shadow-[0_0_0_5px_var(--color-sky-wash)]"
    : counted
      ? "bg-sky-mid"
      : "border-2 border-field bg-white";
  const who = investorLine(r);
  const amount = r.amount == null ? null : formatAmount(r.amount, r.currency ?? "");
  return (
    <li className="flex gap-4">
      <div className="flex w-3.5 flex-col items-center">
        <span className={`mt-[5px] size-3.5 shrink-0 rounded-full ${dot}`} />
        {last ? null : <span className="w-0.5 flex-1 bg-line-soft" />}
      </div>
      <div className={`flex flex-1 flex-col gap-2 ${last ? "pb-2" : "pb-6"}`}>
        <div className="flex justify-between gap-3">
          <span className={`text-[17px] 2xl:text-lg ${thesis ? "font-bold" : "font-semibold"} ${counted ? "text-ink" : "text-faint"}`}>
            {r.label ? stageLabel(r.label) : "Round"}
            {amount ? ` · ${amount}` : ""}
          </span>
          <span className="tabular shrink-0 text-sm text-faint">{formatDate(r.date)}</span>
        </div>
        {thesis ? (
          <span className="inline-flex h-6 w-fit items-center rounded-full bg-sky-dot px-2.5 text-xs font-bold text-sky-deep">In your thesis</span>
        ) : null}
        {counted ? (
          who ? <span className="text-sm leading-normal text-muted 2xl:text-[15px]">{who}</span> : null
        ) : (
          <span className="text-sm text-faint">{who ? `${who}. ${notCountedReason(r)}` : notCountedReason(r)}</span>
        )}
        {r.sources?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {r.sources.map((s, i) => {
              const c = sourceChip(s);
              const href = safeUrl(s.url);
              const cls = `inline-flex h-[26px] items-center rounded-full px-2.5 text-xs font-semibold no-underline ${c.cls}`;
              return href ? (
                <a key={`${s.url}-${i}`} href={href} target="_blank" rel="noopener noreferrer" title={s.name} className={`${cls} hover:underline`}>
                  {c.label} · {c.domain}
                </a>
              ) : (
                <span key={`${s.name}-${i}`} className={cls}>
                  {c.label} · {c.domain}
                </span>
              );
            })}
          </div>
        ) : null}
      </div>
    </li>
  );
}

type NewsItem = NonNullable<DealDetail["recent_news"]>[number];

// "Latest news from Cala": undefined = still loading (skeleton), [] = hidden.
function News({ items }: { items: NewsItem[] | null | undefined }) {
  if (items === undefined) {
    return (
      <section className="mt-8 flex flex-col gap-3" aria-busy="true" aria-label="Loading news">
        <div className="h-5 w-48 animate-pulse rounded bg-chip" />
        {[0, 1].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-2xl bg-chip" />
        ))}
      </section>
    );
  }
  const news = (items ?? []).filter((n) => n?.title).slice(0, MAX_NEWS);
  if (!news.length) return null;
  return (
    <section className="mt-8 flex flex-col gap-3" aria-labelledby="news-title">
      <h3 id="news-title" className="m-0 font-display text-xl font-semibold">
        Latest news from Cala
      </h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {news.map((n, i) => {
          const href = safeUrl(n.url);
          const source = n.source || (n.url ? hostOf(n.url) : null);
          const meta = [source, n.date ? formatDate(n.date, true) : null].filter(Boolean).join(" · ");
          const body = (
            <>
              <span className="text-[15px] font-semibold leading-snug text-ink 2xl:text-base">{n.title}</span>
              {meta ? <span className="tabular text-[13px] text-faint">{meta}</span> : null}
            </>
          );
          const cls = "flex flex-col gap-1 rounded-2xl border border-line-soft bg-page px-4 py-3 no-underline";
          return (
            <li key={`${n.url}-${i}`}>
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer" className={`${cls} transition-colors hover:border-sky-mid hover:bg-sky-wash`}>
                  {body}
                </a>
              ) : (
                <div className={cls}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
