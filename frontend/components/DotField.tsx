import type { Audit } from "@/lib/types";

const MAX_DOTS = 400; // above this one dot stands for several companies

/** "Your thesis market": one dot per company, coloured invested / passed / in review / never seen. */
export function DotField({ summary }: { summary: Audit["summary"] }) {
  const groups = [
    { key: "invested", label: "Invested", n: summary.invested, dot: "bg-mint-dot", num: "text-mint-ink", text: "text-muted" },
    { key: "passed", label: "Passed", n: summary.passed, dot: "bg-mint-mid", num: "text-mint-ink", text: "text-muted" },
    { key: "in_review", label: "In review", n: summary.in_review, dot: "bg-mint-soft ring-1 ring-inset ring-mint-mid", num: "text-mint-ink", text: "text-muted" },
    { key: "never_seen", label: "Never seen", n: summary.never_seen, dot: "bg-sky-dot", num: "text-sky-num", text: "font-semibold text-sky-ink" },
  ];
  const total = groups.reduce((a, g) => a + g.n, 0);
  const per = Math.max(1, Math.ceil(total / MAX_DOTS));
  const dots = groups.flatMap((g) => Array.from({ length: Math.round(g.n / per) }, () => g.dot));
  // 9 columns as in the design for small markets, wider grids for big ones.
  const cols = dots.length <= 54 ? 9 : Math.min(30, Math.ceil(Math.sqrt(dots.length * 2.2)));

  return (
    <figure className="m-0 flex min-w-0 flex-[1_1_420px] flex-col gap-5 rounded-3xl border border-line bg-white p-6 shadow-card sm:p-7">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-display text-lg font-semibold 2xl:text-xl">Your thesis market</span>
        <span className="text-sm text-muted">{per === 1 ? "1 dot = 1 company" : `1 dot ≈ ${per} companies`}</span>
      </div>
      <div
        role="img"
        aria-label={`${summary.market_companies} companies: ${summary.invested} invested, ${summary.passed} passed, ${summary.in_review} in review, ${summary.never_seen} never seen`}
        className="grid gap-[clamp(3px,1vw,10px)]"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: cols > 9 ? "4px" : undefined }}
      >
        {dots.map((cls, i) => (
          <span key={i} className={`aspect-square rounded-full ${cls}`} />
        ))}
      </div>
      <figcaption className="grid grid-cols-2 gap-x-2 gap-y-3 border-t border-line-soft pt-4 sm:grid-cols-4">
        {groups.map((g) => (
          <div key={g.key} className="flex flex-col gap-1">
            <span className={`tabular font-display text-[28px] font-bold leading-none 2xl:text-[32px] ${g.num}`}>{g.n.toLocaleString("en-US")}</span>
            <span className={`flex items-center gap-1.5 text-[13px] 2xl:text-sm ${g.text}`}>
              <span className={`size-2.5 rounded-full ${g.dot}`} />
              {g.label}
            </span>
          </div>
        ))}
      </figcaption>
    </figure>
  );
}
