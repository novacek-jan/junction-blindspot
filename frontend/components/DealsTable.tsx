import type { BlindSpot, Investor } from "@/lib/types";
import { formatAmount, formatDate, safeUrl, stageLabel } from "@/lib/format";
import { monogram, sourceChip } from "@/lib/present";

/** VCs (is_vc; older responses: organisations), leads first: "A, B +3". Angels only when a round names no VC. */
export function vcLine(investors: Investor[] = [], max = 2): string {
  const vcs = investors.filter((i) => i.is_vc ?? i.type !== "Person");
  const list = vcs.length ? vcs : investors;
  const names = [...list.filter((i) => i.is_lead), ...list.filter((i) => !i.is_lead)].map((i) => i.name);
  if (!names.length) return "—";
  return names.length > max ? `${names.slice(0, max).join(", ")} +${names.length - max}` : names.join(", ");
}

const byRoundDateDesc = (a: BlindSpot, b: BlindSpot) => (b.round.date ?? "").localeCompare(a.round.date ?? "");

/** "The {n}, newest first". A row (or Enter on it) opens the side panel. */
export function DealsTable({ rows, onOpen, updated }: { rows: BlindSpot[]; onOpen: (row: BlindSpot) => void; updated?: Set<string> }) {
  const sorted = [...rows].sort(byRoundDateDesc);
  return (
    <section className="flex min-w-0 flex-col overflow-hidden rounded-3xl border border-line bg-white" aria-labelledby="table-title">
      <div className="flex flex-wrap items-end justify-between gap-3 px-5 pb-5 pt-7 sm:px-7">
        <h2 id="table-title" className="m-0 font-display text-[26px] font-semibold tracking-[-0.02em] 2xl:text-[30px]">
          The {sorted.length.toLocaleString("en-US")}, newest first
        </h2>
        <span className="text-sm text-muted 2xl:text-base">Open a company for every round and source</span>
      </div>
      {sorted.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] border-collapse text-[15px] 2xl:text-base">
            <thead>
              <tr className="text-left text-[13px] text-faint 2xl:text-sm">
                <th className="px-5 py-2.5 font-semibold sm:px-7">Company</th>
                <th className="px-3 py-2.5 font-semibold">Round</th>
                <th className="px-3 py-2.5 text-right font-semibold">Amount</th>
                <th className="px-3 py-2.5 font-semibold">VC investors</th>
                <th className="px-3 py-2.5 font-semibold">Raised</th>
                <th className="py-2.5 pl-3 pr-5 font-semibold sm:pr-7">Source</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((d) => {
                const r = d.round;
                const src = r.sources?.[0];
                const chip = src ? sourceChip(src) : null;
                const href = safeUrl(src?.url);
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
                    className="cursor-pointer border-t border-line-soft outline-none transition-colors hover:bg-ice focus-visible:bg-ice"
                  >
                    <td className="px-5 py-3.5 sm:px-7">
                      <div className="flex items-center gap-3.5">
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-sky-wash font-display text-[17px] font-bold text-sky-ink">{monogram(d.name)}</span>
                        <span className="flex min-w-0 flex-col gap-0.5">
                          <span className="flex items-center gap-2 text-base font-semibold text-ink 2xl:text-[17px]">
                            {d.name}
                            {updated?.has(d.company_id) ? (
                              <span title="Round found by the live check with Cala" className="inline-flex h-5 items-center rounded-full bg-mint-soft px-2 text-[11px] font-bold uppercase tracking-wide text-mint-ink">
                                New
                              </span>
                            ) : null}
                          </span>
                          <span className="text-[13px] text-faint 2xl:text-sm">{[d.country, d.website?.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")].filter(Boolean).join(" · ") || "—"}</span>
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3.5">
                      {r.label ? (
                        <span className="inline-flex h-7 items-center whitespace-nowrap rounded-full bg-chip px-3 text-[13px] font-semibold text-ink">{stageLabel(r.label)}</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className={`tabular whitespace-nowrap px-3 py-3.5 text-right font-display text-[17px] font-semibold 2xl:text-lg ${r.amount == null ? "text-[#9AA9B8]" : "text-ink"}`}>
                      {r.amount == null ? "Undisclosed" : formatAmount(r.amount, r.currency ?? "")}
                    </td>
                    <td className="px-3 py-3.5 leading-snug text-muted">{vcLine(r.investors)}</td>
                    <td className="tabular whitespace-nowrap px-3 py-3.5 text-muted">{formatDate(r.date)}</td>
                    <td className="py-3.5 pl-3 pr-5 sm:pr-7">
                      {chip ? (
                        <span className="flex items-center gap-2 whitespace-nowrap">
                          <span className={`inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold ${chip.cls}`}>{chip.label}</span>
                          {href ? (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              title={src!.name}
                              onClick={(e) => e.stopPropagation()}
                              onKeyDown={(e) => e.stopPropagation()}
                              className="text-[13px] text-link underline hover:text-sky-ink 2xl:text-sm"
                            >
                              {chip.domain}
                            </a>
                          ) : (
                            <span className="text-[13px] text-muted">{chip.domain}</span>
                          )}
                        </span>
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
        <p className="px-7 pb-8 text-base text-muted">Every company in this thesis market is already in your CRM.</p>
      )}
    </section>
  );
}
