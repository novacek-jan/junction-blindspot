import type { BlindSpot, Investor } from "@/lib/types";
import { formatAmount, formatDate, safeUrl, stageLabel } from "@/lib/format";

const RANK_LABEL: Record<string, string> = { FILING: "Filing", PRESS: "Press", PRIMARY: "Primary", AGGREGATOR: "Aggregator" };

// Lead investors first, otherwise the backend's order.
function investorNames(investors: Investor[]): string {
  return [...investors.filter((i) => i.is_lead), ...investors.filter((i) => !i.is_lead)].map((i) => i.name).join(", ");
}

/** Rows in the backend's order (round amount, then date). The source is round.sources[0], the strongest one. */
export function DealsTable({ rows }: { rows: BlindSpot[] }) {
  if (!rows.length) return null;

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-300 bg-white">
      <table className="w-full min-w-[900px] border-collapse text-left text-base text-zinc-950">
        <thead className="border-b-2 border-zinc-300 bg-zinc-100 text-sm font-semibold text-zinc-800">
          <tr>
            <th className="px-4 py-3">Company</th>
            <th className="px-4 py-3">Country</th>
            <th className="px-4 py-3">Round</th>
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3 text-right">Amount</th>
            <th className="px-4 py-3">Investors</th>
            <th className="px-4 py-3">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200">
          {rows.map((d) => {
            const r = d.round;
            const src = r.sources?.[0];
            const href = safeUrl(src?.url);
            const srcLabel = src ? [(src.rank && RANK_LABEL[src.rank]) || "Source", src.date ? formatDate(src.date, true) : null].filter(Boolean).join(" · ") : null;
            return (
              <tr key={d.company_id}>
                <td className="px-4 py-3 font-semibold">{d.name}</td>
                <td className="whitespace-nowrap px-4 py-3">{d.country || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3">{r.label ? stageLabel(r.label) : "—"}</td>
                <td className="tabular whitespace-nowrap px-4 py-3">{formatDate(r.date)}</td>
                <td className="tabular whitespace-nowrap px-4 py-3 text-right font-semibold">{formatAmount(r.amount, r.currency ?? "")}</td>
                <td className="px-4 py-3">{r.investors?.length ? investorNames(r.investors) : "—"}</td>
                <td className="whitespace-nowrap px-4 py-3">
                  {src && href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={src.name}
                      className="font-semibold text-sky-800 underline underline-offset-2 hover:text-sky-950"
                    >
                      {srcLabel}
                    </a>
                  ) : (
                    srcLabel ?? "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
