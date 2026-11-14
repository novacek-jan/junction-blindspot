import type { Audit } from "@/lib/types";
import { Card } from "./Heatmap";

export function BlindSpots({ audit }: { audit: Audit }) {
  const spots = audit.top_blind_spots.slice(0, 3);
  const leads = audit.top_missed_leads.slice(0, 5);
  return (
    <Card title="Top blind spots" subtitle="Where your pipeline leaks the most">
      {spots.length ? (
        <ol className="flex flex-col divide-y divide-slate-100">
          {spots.map((s, i) => (
            <li key={s.title} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <span className={`pt-0.5 font-mono text-xs font-bold ${i === 0 ? "text-sky-600" : "text-zinc-400"}`}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="flex flex-col gap-0.5">
                <p className="text-sm font-semibold text-ink">{s.title}</p>
                <p className="text-xs leading-relaxed text-zinc-600">{s.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-zinc-500">No significant blind spots — nice coverage.</p>
      )}

      {leads.length ? (
        <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Leads behind the deals you missed</span>
          <div className="flex flex-wrap gap-1.5">
            {leads.map((l) => (
              <span key={l.id} className="inline-flex items-center gap-1.5 rounded border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700">
                {l.name}
                <span className="tabular font-mono text-[10px] text-sky-600/80">{l.deals}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
