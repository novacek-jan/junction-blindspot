import type { Pattern } from "@/lib/types";

const KIND_LABEL: Record<string, string> = { top_vc: "Investor", country: "Country", stage: "Stage" };

/** "Key patterns" from audit.patterns (deterministic, computed by the backend). The page hides it when empty. */
export function KeyPatterns({ patterns }: { patterns: Pattern[] }) {
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-slate-200/80 bg-white p-6 shadow-card 2xl:p-8">
      <div className="flex flex-col gap-0.5 border-b border-slate-100 pb-4">
        <h2 className="text-lg font-bold tracking-tight text-ink 2xl:text-xl">Key patterns</h2>
        <span className="text-base text-zinc-600">Among the companies you never saw</span>
      </div>
      <ol className="flex flex-col divide-y divide-slate-100">
        {patterns.map((p, i) => {
          const pct = p.total > 0 ? Math.round((100 * p.value) / p.total) : 0;
          return (
            <li key={`${p.kind}-${i}`} className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
              <span className={`tabular pt-0.5 text-base font-bold ${i === 0 ? "text-sky-600" : "text-zinc-500"}`}>{String(i + 1).padStart(2, "0")}</span>
              <div className="flex flex-1 flex-col gap-2">
                <p className="text-lg font-medium leading-snug text-ink 2xl:text-xl">{p.text}</p>
                <div className="flex items-center gap-3">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
                    <div className="h-full rounded-full bg-sky-500" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="tabular shrink-0 text-sm font-semibold uppercase tracking-wider text-zinc-500">
                    {KIND_LABEL[p.kind] ?? p.kind} · {pct}%
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
