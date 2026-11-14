import type { BlindSpot, Investor, Source } from "@/lib/types";
import { formatAmount, formatDate, safeUrl, stageLabel } from "@/lib/format";

export const RANK_LABEL: Record<string, string> = { FILING: "Filing", PRESS: "Press", PRIMARY: "Primary", AGGREGATOR: "Aggregator" };

export function sourceLabel(s: Source): string {
  return [(s.rank && RANK_LABEL[s.rank]) || "Source", s.date ? formatDate(s.date, true) : null].filter(Boolean).join(" · ");
}

// Investor organisations first (leads first); individuals only when a round names no organisation.
function vcInvestors(investors: Investor[] = []): { names: string; angelsOnly: boolean } {
  const orgs = investors.filter((i) => i.type !== "Person");
  const list = orgs.length ? orgs : investors;
  const sorted = [...list.filter((i) => i.is_lead), ...list.filter((i) => !i.is_lead)];
  return { names: sorted.map((i) => i.name).join(", "), angelsOnly: !orgs.length && investors.length > 0 };
}

/** "Companies you never saw". Rows keep the backend's order (round amount, then date); a click opens the side panel. */
export function DealsTable({ rows, onOpen }: { rows: BlindSpot[]; onOpen: (row: BlindSpot) => void }) {
  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-card">
      <div className="flex items-center gap-3 border-b border-slate-200/80 px-6 py-5">
        <h2 className="text-lg font-bold tracking-tight text-ink 2xl:text-xl">Companies you never saw</h2>
        <span className="tabular rounded-md border border-sky-200 bg-sky-50 px-2 py-0.5 text-sm font-semibold text-sky-700">{rows.length}</span>
      </div>
      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-left text-base text-ink 2xl:text-lg">
            <thead className="border-b border-slate-200/80 bg-slate-50/80 text-sm font-semibold uppercase tracking-wider text-zinc-600">
              <tr>
                <th className="px-6 py-3">Company</th>
                <th className="px-4 py-3">Country</th>
                <th className="px-4 py-3">Stage</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3">VC investors</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-6 py-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((d) => {
                const r = d.round;
                const src = r.sources?.[0];
                const href = safeUrl(src?.url);
                const inv = vcInvestors(r.investors);
                return (
                  <tr
                    key={d.company_id}
                    tabIndex={0}
                    aria-label={`${d.name}: open details`}
                    onClick={() => onOpen(d)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onOpen(d);
                      }
                    }}
                    className="cursor-pointer align-top outline-none transition-colors hover:bg-slate-50 focus-visible:bg-sky-50"
                  >
                    <td className="px-6 py-3.5">
                      <div className="flex flex-col items-start gap-1">
                        <span className="font-semibold">{d.name}</span>
                        <span className="whitespace-nowrap rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-xs font-semibold tracking-wide text-sky-700">
                          NOT IN CRM
                        </span>
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3.5 text-zinc-700">{d.country || "—"}</td>
                    <td className="whitespace-nowrap px-4 py-3.5">
                      {r.label ? <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-sm font-medium text-slate-700">{stageLabel(r.label)}</span> : "—"}
                    </td>
                    <td className="tabular whitespace-nowrap px-4 py-3.5 text-right font-semibold">{formatAmount(r.amount, r.currency ?? "")}</td>
                    <td className="px-4 py-3.5">
                      {inv.names ? (
                        <span className={inv.angelsOnly ? "text-zinc-500" : ""} title={inv.angelsOnly ? "Angel investors only" : undefined}>
                          {inv.names}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="tabular whitespace-nowrap px-4 py-3.5 text-zinc-700">{formatDate(r.date)}</td>
                    <td className="whitespace-nowrap px-6 py-3.5">
                      {src && href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={src.name}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                          className="font-semibold text-sky-800 underline underline-offset-2 hover:text-sky-950"
                        >
                          {sourceLabel(src)}
                        </a>
                      ) : src ? (
                        sourceLabel(src)
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-6 py-8 text-base text-zinc-600">Every company in this thesis market is already in your CRM.</p>
      )}
    </section>
  );
}
