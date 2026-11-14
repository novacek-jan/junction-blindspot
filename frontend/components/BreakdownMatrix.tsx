import type { BreakdownCell } from "@/lib/types";
import { stageLabel } from "@/lib/format";

const MIN_MARKET = 3; // below this a share is too noisy to colour

function tone(c: BreakdownCell): string {
  if (c.market < MIN_MARKET) return "bg-slate-50 text-zinc-500 border border-dashed border-slate-200";
  const share = c.never_seen / c.market;
  if (share > 0.75) return "bg-sky-100 text-sky-800 border border-sky-300 font-semibold";
  if (share >= 0.5) return "bg-slate-200 text-slate-800 border border-slate-300 font-semibold";
  return "bg-slate-100 text-slate-700 border border-slate-200";
}

/** Country × stage from audit.breakdown: share of the thesis market never seen, coloured only when market >= 3. */
export function BreakdownMatrix({ cells }: { cells: BreakdownCell[] }) {
  // Backend order: countries alphabetically, stages in stage order.
  const countries = [...new Set(cells.map((c) => c.country))];
  const stages = [...new Set(cells.map((c) => c.stage))];
  const at = new Map(cells.map((c) => [`${c.country}|${c.stage}`, c]));

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-slate-200/80 bg-white p-6 shadow-card 2xl:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-lg font-bold tracking-tight text-ink 2xl:text-xl">Never seen by country &amp; stage</h2>
          <span className="text-base text-zinc-600">Share of the thesis market not in your CRM</span>
        </div>
        <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-zinc-600" aria-label="Legend">
          <Legend cls="bg-slate-100 border border-slate-200" label="<50%" />
          <Legend cls="bg-slate-200 border border-slate-300" label="50–75%" />
          <Legend cls="bg-sky-100 border border-sky-300" label=">75%" />
          <Legend cls="bg-slate-50 border border-dashed border-slate-300" label={`under ${MIN_MARKET} companies`} />
        </ul>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-base 2xl:text-lg">
          <thead className="text-sm font-semibold uppercase tracking-wider text-zinc-600">
            <tr>
              <th className="py-2 pr-3">Country</th>
              {stages.map((s) => (
                <th key={s} className="px-2 py-2 text-center">
                  {stageLabel(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {countries.map((country) => (
              <tr key={country}>
                <td className="py-2.5 pr-3 font-medium text-ink">{country}</td>
                {stages.map((stage) => {
                  const c = at.get(`${country}|${stage}`);
                  if (!c || c.market === 0) {
                    return (
                      <td key={stage} className="px-2 py-2.5 text-center text-zinc-400">
                        —
                      </td>
                    );
                  }
                  const label = `${c.never_seen} of ${c.market}`;
                  return (
                    <td key={stage} className="px-2 py-2.5 text-center">
                      <span
                        className={`tabular inline-flex min-w-[5.5rem] flex-col items-center rounded-md px-2 py-1 ${tone(c)}`}
                        title={`${country}, ${stageLabel(stage)}: ${label} never seen`}
                      >
                        {c.market >= MIN_MARKET ? (
                          <>
                            <span>{Math.round((100 * c.never_seen) / c.market)}%</span>
                            <span className="text-xs font-normal opacity-80">{label}</span>
                          </>
                        ) : (
                          <span className="text-sm">{label}</span>
                        )}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span className={`size-3 rounded-sm ${cls}`} />
      {label}
    </li>
  );
}
