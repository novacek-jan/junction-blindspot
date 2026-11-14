import type { BlindSpot, Briefing as BriefingT } from "@/lib/types";

const CARD = [
  { box: "bg-sky-wash", num: "text-sky-num" },
  { box: "bg-mint-wash", num: "text-mint-ink" },
  { box: "border border-line bg-white", num: "text-sky-num" },
];
const MAX_CHIPS = 4;

/** "Why they slipped through": up to 3 cards from audit.briefing.insights. Company chips open the side panel. */
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
          const companies = ins.company_ids.map((id) => byId.get(id)).filter((r): r is BlindSpot => !!r);
          const investors = ins.investor_names.slice(0, MAX_CHIPS);
          // Four chips at most: investors first, then companies, the last slot becomes "+N" when they don't fit.
          const room = Math.max(0, MAX_CHIPS - investors.length);
          const shown = companies.length <= room ? companies : companies.slice(0, Math.max(0, room - 1));
          const more = companies.length - shown.length;
          return (
            <article key={`${ins.kind}-${i}`} className={`flex min-w-0 flex-col gap-4 rounded-3xl px-7 pb-7 pt-8 ${style.box}`}>
              <div className="flex items-baseline gap-2.5">
                <span className={`tabular font-display text-[72px] font-bold leading-[0.85] tracking-[-0.05em] sm:text-[84px] 2xl:text-[96px] ${style.num}`}>{ins.value}</span>
                <span className="text-[17px] font-semibold text-muted">of the {ins.total}</span>
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
                      className="inline-flex h-[34px] items-center rounded-full bg-white px-3.5 text-[15px] font-semibold text-ink transition-shadow hover:shadow-[0_0_0_2px_var(--color-sky-dot)]"
                    >
                      {r.name}
                    </button>
                  ))}
                  {more > 0 ? <span className="inline-flex h-[34px] items-center rounded-full bg-white px-3.5 text-[15px] font-semibold text-muted">+{more}</span> : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function SparkIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2F86CC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    </svg>
  );
}
