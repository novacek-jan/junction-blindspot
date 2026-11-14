/**
 * Loading state of the results page in the design/claude layout: hero (eyebrow, headline, thesis chips, live line),
 * the "Your thesis market" dot card, "Why they slipped through" with three cards, and the table.
 * `message` is shown as a status line with a spinner (e.g. while a real audit runs).
 */
export function ResultsSkeleton({ message }: { message?: string }) {
  return (
    <div
      className="mx-auto flex w-full max-w-[1240px] flex-col gap-12 px-5 pb-[72px] pt-4 sm:px-10 sm:pt-6 2xl:max-w-[1480px] 2xl:gap-14"
      aria-busy="true"
      aria-label="Loading audit"
    >
      <section className="flex flex-wrap items-center gap-10 sm:gap-12">
        <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-6">
          {message ? (
            <span role="status" className="inline-flex items-center gap-2.5 text-[15px] font-semibold text-sky-ink">
              <span className="relative flex size-2.5" aria-hidden="true">
                <span className="absolute inset-0 animate-ping rounded-full bg-sky-dot opacity-60 motion-reduce:hidden" />
                <span className="relative size-2.5 rounded-full bg-sky-dot" />
              </span>
              {message}
            </span>
          ) : (
            <Bar className="h-4 w-72" />
          )}
          <div className="flex flex-col gap-3">
            <Bar className="h-12 w-full rounded-xl sm:h-[58px]" />
            <Bar className="h-12 w-11/12 rounded-xl sm:h-[58px]" />
            <Bar className="h-12 w-3/5 rounded-xl sm:h-[58px]" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Bar className="mr-1 h-4 w-40" />
            <span className="h-[34px] w-36 animate-pulse rounded-full bg-sky-wash" />
            <span className="h-[34px] w-24 animate-pulse rounded-full bg-mint-wash" />
            <span className="h-[34px] w-44 animate-pulse rounded-full border border-line bg-white" />
          </div>
          <Bar className="h-3.5 w-80" />
        </div>

        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-5 rounded-3xl border border-line bg-white p-6 shadow-card sm:p-7">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-display text-lg font-semibold text-faint 2xl:text-xl">Your thesis market</span>
            <Bar className="h-3.5 w-24" />
          </div>
          <div className="grid grid-cols-9 gap-[clamp(3px,1vw,10px)]" aria-hidden="true">
            {Array.from({ length: 36 }, (_, i) => (
              <span
                key={i}
                className="aspect-square animate-pulse rounded-full bg-line"
                style={{ animationDelay: `${(i % 9) * 70 + Math.floor(i / 9) * 40}ms` }}
              />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-3 border-t border-line-soft pt-4 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-2">
                <Bar className="h-7 w-10" />
                <Bar className="h-3 w-16" />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-6">
        <span className="font-display text-[32px] font-bold leading-tight tracking-[-0.03em] text-line sm:text-[40px] 2xl:text-[44px]">
          Why they slipped through
        </span>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {[
            { box: "bg-sky-wash", fill: "[&_span]:bg-white/80" },
            { box: "bg-mint-wash", fill: "[&_span]:bg-white/80" },
            { box: "border border-line bg-white", fill: "[&_span]:bg-line-soft" },
          ].map(({ box, fill }, i) => (
            <div key={i} className={`flex animate-pulse flex-col gap-4 rounded-3xl px-7 pb-7 pt-8 ${box} ${fill}`}>
              <div className="flex items-baseline gap-2.5">
                <span className="h-[72px] w-20 rounded-xl bg-white/80 sm:h-[84px]" />
                <span className="h-4 w-12 rounded bg-white/80" />
              </div>
              <span className="h-7 w-4/5 rounded-lg bg-white/80" />
              <span className="h-4 w-full rounded bg-white/70" />
              <span className="h-4 w-2/3 rounded bg-white/70" />
              <div className="mt-2 flex gap-2">
                <span className="h-[34px] w-24 rounded-full bg-white/80" />
                <span className="h-[34px] w-28 rounded-full bg-white/80" />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col overflow-hidden rounded-3xl border border-line bg-white">
        <div className="px-5 pb-5 pt-7 sm:px-7">
          <Bar className="h-7 w-56" />
        </div>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3.5 border-t border-line-soft px-5 py-4 sm:px-7">
            <span className="size-10 shrink-0 animate-pulse rounded-xl bg-sky-wash" />
            <div className="flex flex-1 flex-col gap-2">
              <Bar className="h-4 w-40" />
              <Bar className="h-3 w-28" />
            </div>
            <Bar className="hidden h-6 w-16 rounded-full sm:block" />
            <Bar className="hidden h-4 w-48 md:block" />
          </div>
        ))}
      </section>
    </div>
  );
}

function Bar({ className }: { className: string }) {
  return <span className={`block animate-pulse rounded bg-line ${className}`} />;
}
