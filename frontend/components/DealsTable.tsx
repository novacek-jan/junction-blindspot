import type { NeverSeenDeal, Source } from "@/lib/types";
import { byDateDesc, formatAmount, formatDate, safeUrl, stageLabel } from "@/lib/format";

// Best source per row: filing, then press, then primary, aggregator, unranked.
const RANK_ORDER = ["FILING", "PRESS", "PRIMARY", "AGGREGATOR", null] as const;
const RANK_LABEL: Record<string, string> = { FILING: "Filing", PRESS: "Press", PRIMARY: "Primary", AGGREGATOR: "Aggregator" };

function primarySource(sources: Source[] | undefined): (Source & { href: string }) | null {
  for (const rank of RANK_ORDER) {
    const s = sources?.find((x) => (x.rank ?? null) === rank && safeUrl(x.url));
    if (s) return { ...s, href: safeUrl(s.url)! };
  }
  return null;
}

export function DealsTable({ deals }: { deals: NeverSeenDeal[] }) {
  const rows = [...deals].sort(byDateDesc);
  if (!rows.length) return null;

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-300 bg-white">
      <table className="w-full min-w-[900px] border-collapse text-left text-base text-zinc-950">
        <thead className="border-b-2 border-zinc-300 bg-zinc-100 text-sm font-semibold text-zinc-800">
          <tr>
            <th className="px-4 py-3">Company</th>
            <th className="px-4 py-3">Country</th>
            <th className="px-4 py-3">Stage</th>
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3 text-right">Amount</th>
            <th className="px-4 py-3">Investors</th>
            <th className="px-4 py-3">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200">
          {rows.map((d) => {
            const src = primarySource(d.sources);
            return (
              <tr key={d.company_id}>
                <td className="px-4 py-3 font-semibold">{d.name}</td>
                <td className="whitespace-nowrap px-4 py-3">{d.country || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3">{d.stage ? stageLabel(d.stage) : "—"}</td>
                <td className="tabular whitespace-nowrap px-4 py-3">{formatDate(d.date)}</td>
                <td className="tabular whitespace-nowrap px-4 py-3 text-right font-semibold">{formatAmount(d.amount, d.currency)}</td>
                <td className="px-4 py-3">{d.lead_investors?.length ? d.lead_investors.map((l) => l.name).join(", ") : "—"}</td>
                <td className="whitespace-nowrap px-4 py-3">
                  {src ? (
                    <a
                      href={src.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={src.name}
                      className="font-semibold text-sky-800 underline underline-offset-2 hover:text-sky-950"
                    >
                      {(src.rank && RANK_LABEL[src.rank]) || "Source"}
                    </a>
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
  );
}
