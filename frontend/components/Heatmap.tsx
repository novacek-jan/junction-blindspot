import type { Audit, HeatmapCell } from "@/lib/types";
import { pct, stageLabel } from "@/lib/format";

function tone(share: number) {
  if (share > 0.75) return "bg-sky-100 text-sky-700 border-sky-200 font-semibold";
  if (share >= 0.5) return "bg-slate-200 text-slate-700 border-transparent";
  return "bg-slate-100 text-slate-600 border-transparent";
}

export function Heatmap({ heatmap }: { heatmap: Audit["heatmap"] }) {
  const byKey = new Map<string, HeatmapCell>(heatmap.cells.map((c) => [`${c.country}|${c.stage}`, c]));

  return (
    <Card title="Missed deals by country × stage" subtitle="Share of peer deals that never reached your pipeline">
      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] text-zinc-500">
        <Swatch cls="bg-slate-100" label="<50%" />
        <Swatch cls="bg-slate-200" label="50–75%" />
        <Swatch cls="bg-sky-100" label=">75%" />
      </div>
      <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] uppercase text-zinc-500">
              <th className="py-2 pr-2 font-semibold">Country</th>
              {heatmap.stages.map((s) => (
                <th key={s} className="px-2 py-2 text-center font-semibold whitespace-nowrap">
                  {stageLabel(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {heatmap.countries.map((country) => (
              <tr key={country} className="transition-colors hover:bg-slate-50/70">
                <td className="py-2 pr-2 font-medium whitespace-nowrap text-ink">{country}</td>
                {heatmap.stages.map((stage) => {
                  const c = byKey.get(`${country}|${stage}`);
                  return (
                    <td key={stage} className="px-2 py-2 text-center">
                      {c && c.total > 0 ? (
                        <span
                          title={`${country} · ${stageLabel(stage)}: missed ${c.never_seen} of ${c.total}`}
                          className={`tabular inline-flex min-w-[3.25rem] flex-col items-center rounded border px-2 py-0.5 font-mono ${tone(c.share)}`}
                        >
                          <span>{pct(c.share)}</span>
                          <span className="text-[9px] font-normal opacity-70">
                            {c.never_seen}/{c.total}
                          </span>
                        </span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Swatch({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`size-2.5 rounded-sm border border-slate-300/70 ${cls}`} />
      {label}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-xl border border-slate-200/80 bg-white p-5 shadow-[var(--shadow-card)] sm:p-6">
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
        <div className="flex flex-col">
          <h2 className="text-sm font-bold uppercase tracking-wide text-ink">{title}</h2>
          {subtitle ? <span className="text-xs text-zinc-500">{subtitle}</span> : null}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}
