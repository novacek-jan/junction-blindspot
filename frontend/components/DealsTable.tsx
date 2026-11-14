"use client";

import { useMemo, useState } from "react";
import type { NeverSeenDeal } from "@/lib/types";
import { formatAmount, formatDate, stageLabel } from "@/lib/format";
import { SourceIcons } from "./Sources";
import { Icon } from "./Icon";

type SortKey = "date" | "amount" | "name";
const PAGE = 25;

export function StageBadge({ stage }: { stage: string }) {
  const seed = stage === "SEED" || stage === "PRE_SEED";
  return (
    <span
      className={`inline-block whitespace-nowrap rounded border px-2 py-0.5 font-mono text-[11px] ${
        seed ? "border-green-200 bg-green-100 text-green-700" : "border-slate-200 bg-slate-100 text-slate-700"
      }`}
    >
      {stageLabel(stage)}
    </span>
  );
}

export function DealsTable({
  deals,
  total,
  selectedId,
  onOpen,
}: {
  deals: NeverSeenDeal[];
  total: number;
  selectedId?: string | null;
  onOpen: (deal: NeverSeenDeal) => void;
}) {
  const [sort, setSort] = useState<SortKey>("date");
  const [limit, setLimit] = useState(PAGE);

  const sorted = useMemo(() => {
    const d = [...deals];
    if (sort === "date") d.sort((a, b) => b.date.localeCompare(a.date));
    if (sort === "amount") d.sort((a, b) => b.amount - a.amount); // mixed currencies: rough order only
    if (sort === "name") d.sort((a, b) => a.name.localeCompare(b.name));
    return d;
  }, [deals, sort]);

  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/80 p-5">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-ink">Deals you never saw</h2>
          <span className="tabular rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
            {total} missed
          </span>
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-medium text-ink outline-none focus:border-ink"
          >
            <option value="date">Most recent</option>
            <option value="amount">Largest round</option>
            <option value="name">Company A–Z</option>
          </select>
        </label>
      </div>

      {sorted.length === 0 ? (
        <p className="p-6 text-sm text-zinc-500">No never-seen deals in this audit.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-xs">
            <thead className="border-b border-slate-200/80 bg-slate-50/80 text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Company</th>
                <th className="px-4 py-3 font-semibold">Country</th>
                <th className="px-4 py-3 font-semibold">Stage</th>
                <th className="px-4 py-3 text-right font-semibold">Amount</th>
                <th className="px-4 py-3 font-semibold">Date</th>
                <th className="px-4 py-3 font-semibold">Lead investor</th>
                <th className="px-5 py-3 font-semibold">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sorted.slice(0, limit).map((d) => (
                <tr
                  key={d.company_id}
                  tabIndex={0}
                  onClick={() => onOpen(d)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(d))}
                  className={`group cursor-pointer outline-none transition-colors hover:bg-slate-50 focus-visible:bg-sky-50/60 ${
                    selectedId === d.company_id ? "bg-sky-50/60" : ""
                  }`}
                >
                  <td className="px-5 py-3">
                    <div className="flex flex-col">
                      <span className="flex items-center gap-1.5 font-semibold text-ink">
                        {d.name}
                        {d.conflated ? <ConflatedFlag /> : null}
                      </span>
                      <span className="text-[11px] text-zinc-400">{d.website}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-600">{d.country}</td>
                  <td className="px-4 py-3">
                    <StageBadge stage={d.stage} />
                  </td>
                  <td className="tabular px-4 py-3 text-right font-mono font-semibold text-ink">{formatAmount(d.amount, d.currency)}</td>
                  <td className="tabular px-4 py-3 whitespace-nowrap font-mono text-zinc-500">{formatDate(d.date)}</td>
                  <td className="px-4 py-3 font-medium text-ink">
                    {d.lead_investors.length ? d.lead_investors.map((l) => l.name).join(", ") : <span className="text-zinc-400">—</span>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <SourceIcons sources={d.sources} />
                      <Icon name="chevronRight" className="size-4 text-zinc-300 transition-colors group-hover:text-ink" />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sorted.length > limit ? (
        <button
          type="button"
          onClick={() => setLimit((l) => l + PAGE)}
          className="border-t border-slate-100 py-3 text-xs font-medium text-zinc-600 transition-colors hover:bg-slate-50 hover:text-ink"
        >
          Show more ({sorted.length - limit} remaining)
        </button>
      ) : deals.length < total ? (
        <p className="border-t border-slate-100 px-5 py-3 text-[11px] text-zinc-400">
          Showing {deals.length} of {total} never-seen deals with verified round data.
        </p>
      ) : null}
    </section>
  );
}

export function ConflatedFlag() {
  return (
    <span
      title="Cala may have merged several rounds into this record; amount and date are approximate."
      className="inline-flex items-center gap-0.5 rounded border border-amber-200 bg-amber-50 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-700"
    >
      <Icon name="warning" className="size-2.5" />
      merged
    </span>
  );
}
