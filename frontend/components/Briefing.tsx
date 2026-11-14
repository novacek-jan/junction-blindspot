import type { BlindSpot, Briefing as BriefingT } from "@/lib/types";

const CARD = [
  { box: "bg-sky-wash", num: "text-sky-num", chip: "bg-white" },
  { box: "bg-mint-wash", num: "text-mint-ink", chip: "bg-white" },
  { box: "border border-line bg-white", num: "text-sky-num", chip: "bg-chip" },
];
const MAX_CHIPS = 4;

/**
 * "Why they slipped through": up to 3 cards from audit.briefing.insights, in the API's order, whatever their kind.
 * Big number = value, "of {total}" under it. Chips: sector names (coverage) or investors then companies; company
 * chips open the side panel.
 */
export function Briefing({ briefing, rows, onOpen }: { briefing: BriefingT; rows: BlindSpot[]; onOpen: (row: BlindSpot) => void }) {
  const byId = new Map(rows.map((r) => [r.company_id, r]));
  const insights = briefing.insights.filter((i) => i.title && i.value > 0).slice(0, 3);
  if (!insights.length) return null;
  const byClaude = briefing.model && briefing.model !== "template";

  return (
    <section className="flex flex-col gap-6" aria-labelledby="briefing-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h2 id="briefing-title" className="m-0 font-display text-[32px] font-bold leading-tight tracking-[-0.03em] sm:text-[40px] 2xl:text-[44px]">
          Why they slipped through
        </h2>
        <span className="inline-flex items-center gap-2 text-[15px] text-muted">
          <SparkIcon />
          {byClaude ? "Analysis by Claude, from public Cala data only" : "From public Cala data only"}
        </span>
      </div>
      <div className={`grid grid-cols-1 gap-5 ${insights.length === 3 ? "lg:grid-cols-3" : insights.length === 2 ? "lg:grid-cols-2" : ""}`}>
        {insights.map((ins, i) => {
          const style = CARD[i % CARD.length];
          const sectors = sectorNames(ins);
          const companies = sectors.length ? [] : (ins.company_ids ?? []).map((id) => byId.get(id)).filter((r): r is BlindSpot => !!r);
          const investors = sectors.length ? sectors.slice(0, MAX_CHIPS) : (ins.investor_names ?? []).slice(0, MAX_CHIPS);
          // Four chips at most: investors first, then companies, the last slot becomes "+N" when they don't fit.
          const room = Math.max(0, MAX_CHIPS - investors.length);
          const shown = companies.length <= room ? companies : companies.slice(0, Math.max(0, room - 1));
          const more = companies.length - shown.length;
          return (
            <article key={`${ins.kind}-${i}`} className={`flex min-w-0 flex-col gap-4 rounded-3xl px-7 pb-7 pt-8 ${style.box}`}>
              <div className="flex items-baseline gap-2.5">
                <span className={`tabular font-display text-[72px] font-bold leading-[0.85] tracking-[-0.05em] sm:text-[84px] 2xl:text-[96px] ${style.num}`}>{ins.value}</span>
                {ins.total > 0 ? <span className="text-[17px] font-semibold text-muted">of {ins.total.toLocaleString("en-US")}</span> : null}
              </div>
              <h3 className="m-0 font-display text-[26px] font-bold leading-[1.15] tracking-[-0.02em] 2xl:text-[28px]">{ins.title}</h3>
              <p className="m-0 text-[17px] leading-normal text-body 2xl:text-lg">{ins.line}</p>
              {investors.length || companies.length ? (
                <div className="mt-auto flex flex-wrap gap-2 pt-2">
                  {investors.map((name) => (
                    <span key={`inv-${name}`} className="inline-flex h-[34px] items-center rounded-full bg-white/70 px-3.5 text-[15px] font-semibold text-muted ring-1 ring-inset ring-line">
                      {name}
                    </span>
                  ))}
                  {shown.map((r) => (
                    <button
                      key={r.company_id}
                      type="button"
                      onClick={() => onOpen(r)}
                      className={`inline-flex h-[34px] items-center rounded-full ${style.chip} px-3.5 text-[15px] font-semibold text-ink transition-shadow hover:shadow-[0_0_0_2px_var(--color-sky-dot)]`}
                    >
                      {r.name}
                    </button>
                  ))}
                  {more > 0 ? <span className={`inline-flex h-[34px] items-center rounded-full ${style.chip} px-3.5 text-[15px] font-semibold text-muted`}>+{more}</span> : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

/** Coverage: "Software · 22% seen" (worst first, then best), shown as chips instead of companies. */
function sectorNames(ins: BriefingT["insights"][number]): string[] {
  const chip = (name?: string | null, pct?: number | null) => (name ? (typeof pct === "number" ? `${name} · ${pct}% seen` : name) : null);
  return [chip(ins.worst_industry, ins.worst_pct), chip(ins.best_industry, ins.best_pct)].filter((x): x is string => !!x);
}

function SparkIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2F86CC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    </svg>
  );
}
