"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import type { BlindSpot, Briefing as BriefingT, Insight } from "@/lib/types";

const CARD = [
  {
    box: "bg-sky-wash",
    num: "text-sky-num",
    company: "bg-white",
    label: "bg-white/60 ring-sky-mid/60",
  },
  {
    box: "bg-mint-wash",
    num: "text-mint-ink",
    company: "bg-white",
    label: "bg-white/60 ring-mint-mid",
  },
  {
    box: "border border-line bg-white",
    num: "text-sky-num",
    company: "bg-chip",
    label: "bg-white ring-line",
  },
];
const FIRST_COMPANIES = 3;

/**
 * "Why they slipped through": up to 3 cards from audit.briefing.insights, in the API's order (Claude's pick).
 * Card: big value, "of {total}", title, line, label chips (insight.chips, plain), then the companies
 * (insight.company_ids, names from never_seen): the first 3 and a "+N" button that expands the card in place.
 * Every company chip opens the side panel. Expanded state lives here, so closing the panel keeps it.
 */
export function Briefing({
  briefing,
  rows,
  onOpen,
}: {
  briefing: BriefingT;
  rows: BlindSpot[];
  onOpen: (row: BlindSpot) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const gridRef = useRef<HTMLDivElement>(null);
  useEqualCollapsedHeight(gridRef);
  const byId = new Map(rows.map((r) => [r.company_id, r]));
  const insights = briefing.insights
    .filter((i) => i.title && i.value > 0)
    .slice(0, 3);
  if (!insights.length) return null;
  const byClaude = briefing.model && briefing.model !== "template";

  return (
    <section className="flex flex-col gap-6" aria-labelledby="briefing-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h2
          id="briefing-title"
          className="m-0 font-display text-[32px] font-bold leading-tight tracking-[-0.03em] sm:text-[40px] 2xl:text-[44px]"
        >
          Why they slipped through
        </h2>
        <span className="inline-flex items-center gap-2 text-[15px] text-muted">
          <SparkIcon />
          {byClaude
            ? "Written by Claude from public Cala data and anonymous counts."
            : "From public Cala data and anonymous counts."}
        </span>
      </div>
      <div
        ref={gridRef}
        className={`grid grid-cols-1 items-start gap-5 ${insights.length === 3 ? "lg:grid-cols-3" : insights.length === 2 ? "lg:grid-cols-2" : ""}`}
      >
        {insights.map((ins, i) => {
          const key = `${ins.fact_id ?? ins.kind}-${i}`;
          return (
            <InsightCard
              key={key}
              insight={ins}
              style={CARD[i % CARD.length]}
              companies={(ins.company_ids ?? [])
                .map((id) => byId.get(id))
                .filter((r): r is BlindSpot => !!r)}
              expanded={!!expanded[key]}
              onToggle={() => setExpanded((e) => ({ ...e, [key]: !e[key] }))}
              onOpen={onOpen}
            />
          );
        })}
      </div>
    </section>
  );
}

function InsightCard({
  insight: ins,
  style,
  companies,
  expanded,
  onToggle,
  onOpen,
}: {
  insight: Insight;
  style: (typeof CARD)[number];
  companies: BlindSpot[];
  expanded: boolean;
  onToggle: () => void;
  onOpen: (row: BlindSpot) => void;
}) {
  const listId = useId();
  const labels = (ins.chips ?? [])
    .map((c) => labelText(ins, c.label))
    .filter(Boolean);
  const hidden = Math.max(0, companies.length - FIRST_COMPANIES);
  const shown = expanded ? companies : companies.slice(0, FIRST_COMPANIES);
  const [outerRef, innerRef] = useAnimatedHeight<HTMLDivElement>(expanded);

  return (
    <article
      data-expanded={expanded ? "true" : undefined}
      className={`flex min-w-0 flex-col gap-4 rounded-3xl px-7 pb-7 pt-8 ${style.box}`}
    >
      <div className="flex items-baseline gap-2.5">
        <span
          className={`tabular font-display text-[72px] font-bold leading-[0.85] tracking-[-0.05em] sm:text-[84px] 2xl:text-[96px] ${style.num}`}
        >
          {ins.value}
        </span>
        {ins.total > 0 ? (
          <span className="text-[17px] font-semibold text-muted">
            of {ins.total.toLocaleString("en-US")}
          </span>
        ) : null}
      </div>
      <h3 className="m-0 font-display text-[26px] font-bold leading-[1.15] tracking-[-0.02em] 2xl:text-[28px]">
        {ins.title}
      </h3>
      <p className="m-0 text-[17px] leading-normal text-body 2xl:text-lg">
        {ins.line}
      </p>

      <div className="mt-auto flex flex-col gap-3 pt-1">
        {labels.length ? (
          <ul
            className="m-0 flex list-none flex-wrap gap-2 p-0"
            aria-label="Details"
          >
            {labels.map((label, i) => (
              <li
                key={`${label}-${i}`}
                className={`inline-flex h-[34px] items-center rounded-full px-3.5 text-[15px] font-semibold text-muted ring-1 ring-inset ${style.label}`}
              >
                {label}
              </li>
            ))}
          </ul>
        ) : null}

        {companies.length ? (
          <div
            ref={outerRef}
            className="-m-1 overflow-hidden p-1 transition-[height] duration-300 ease-out motion-reduce:transition-none"
          >
            <div ref={innerRef} className="flex flex-wrap gap-2 pt-1">
              <ul
                id={listId}
                className="contents m-0 list-none p-0"
                aria-label={`${companies.length} ${companies.length === 1 ? "company" : "companies"}`}
              >
                {shown.map((r, i) => (
                  <li
                    key={r.company_id}
                    className={`contents ${i >= FIRST_COMPANIES ? "[&>button]:animate-fade-in" : ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => onOpen(r)}
                      className={`inline-flex h-[38px] items-center rounded-full ${style.company} px-4 text-base font-semibold text-ink shadow-[0_1px_0_rgba(11,31,51,0.06)] transition-shadow hover:shadow-[0_0_0_2px_var(--color-sky-dot)] focus-visible:shadow-[0_0_0_3px_var(--color-sky-dot)] focus-visible:outline-none`}
                    >
                      {r.name}
                    </button>
                  </li>
                ))}
              </ul>
              {hidden > 0 ? (
                <button
                  type="button"
                  onClick={onToggle}
                  aria-expanded={expanded}
                  aria-controls={listId}
                  aria-label={
                    expanded
                      ? "Show fewer companies"
                      : `Show ${hidden} more ${hidden === 1 ? "company" : "companies"}`
                  }
                  className="inline-flex h-[38px] items-center gap-1.5 rounded-full bg-ink px-4 text-base font-semibold text-white transition-colors hover:bg-ink-hover focus-visible:shadow-[0_0_0_3px_var(--color-sky-dot)] focus-visible:outline-none"
                >
                  {expanded ? "Show less" : `+${hidden}`}
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    className={`transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

/** Sector labels arrive lower-case ("energy 67%"): capitalise the first letter on coverage insights. */
function labelText(ins: Insight, label: string): string {
  const t = (label ?? "").trim();
  return t && ins.kind.startsWith("coverage")
    ? t[0].toUpperCase() + t.slice(1)
    : t;
}

/**
 * Animates the outer element's height between the inner content's old and new height whenever `dep` changes,
 * then returns to `auto` so wrapping on resize keeps working.
 */
function useAnimatedHeight<T extends HTMLElement>(dep: unknown) {
  const outer = useRef<T>(null);
  const inner = useRef<HTMLDivElement>(null);
  const last = useRef<number | null>(null);
  useLayoutEffect(() => {
    const o = outer.current;
    const i = inner.current;
    if (!o || !i) return;
    const to = i.offsetHeight;
    const from = last.current;
    last.current = to;
    if (
      from == null ||
      from === to ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    o.dataset.animating = "true";
    o.style.height = `${from + 8}px`; // + p-1 padding (top and bottom)
    void o.offsetHeight; // reflow, so the transition starts from `from`
    o.style.height = `${to + 8}px`;
    const done = () => {
      o.style.height = "";
      delete o.dataset.animating;
      o.removeEventListener("transitionend", done);
    };
    o.addEventListener("transitionend", done);
    const t = window.setTimeout(done, 450);
    return () => {
      window.clearTimeout(t);
      o.removeEventListener("transitionend", done);
    };
  }, [dep]);
  return [outer, inner] as const;
}

/**
 * Collapsed cards share one height: the tallest collapsed card's natural height becomes every card's min-height
 * (the grid uses items-start, so an expanded card grows alone and the others never stretch further; the chip
 * block has mt-auto, so chip rows line up at the bottom). Cards that are expanded or animating keep their last
 * collapsed measurement. Re-measured on resize; cleared when the cards stack in one column.
 */
function useEqualCollapsedHeight(
  gridRef: React.RefObject<HTMLDivElement | null>,
) {
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    const collapsed = new WeakMap<HTMLElement, number>();
    let frame = 0;
    const measure = () => {
      const cards = [...grid.children] as HTMLElement[];
      const columns = getComputedStyle(grid)
        .gridTemplateColumns.split(" ")
        .filter(Boolean).length;
      if (columns < 2) {
        cards.forEach((c) => (c.style.minHeight = ""));
        return;
      }
      for (const c of cards) {
        if (c.dataset.expanded || c.querySelector("[data-animating]")) continue;
        const prev = c.style.minHeight;
        c.style.minHeight = "";
        collapsed.set(c, c.offsetHeight);
        c.style.minHeight = prev;
      }
      const max = Math.max(0, ...cards.map((c) => collapsed.get(c) ?? 0));
      cards.forEach((c) => (c.style.minHeight = max ? `${max}px` : ""));
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    measure();
    const ro = new ResizeObserver(schedule);
    ro.observe(grid);
    for (const c of grid.children) ro.observe(c);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
    };
  }, [gridRef]);
}

function SparkIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="#2F86CC"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    </svg>
  );
}
