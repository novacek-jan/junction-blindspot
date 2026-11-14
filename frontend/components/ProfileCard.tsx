import type { FundProfile } from "@/lib/types";
import { pct, stageLabel } from "@/lib/format";
import { SourceList } from "./Sources";

export function ProfileCard({ profile }: { profile: FundProfile }) {
  const stages = [...profile.stages].sort((a, b) => b.share - a.share);
  const countries = [...profile.countries].sort((a, b) => b.count - a.count);
  const industries = [...profile.industries].sort((a, b) => b.count - a.count);

  return (
    <section className="animate-fade-in flex flex-col gap-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Investments since 2022">
          <span className="tabular">{profile.investments_since_2022}</span> deals
        </Stat>
        <Stat label="Stages">
          <List items={stages.slice(0, 3).map((s) => `${stageLabel(s.label)} ${pct(s.share)}`)} />
        </Stat>
        <Stat label="Countries">
          <List items={countries.slice(0, 3).map((c) => `${c.name} (${c.count})`)} />
        </Stat>
        <Stat label="Industries">
          <List items={industries.slice(0, 3).map((c) => `${c.name} (${c.count})`)} />
        </Stat>
      </div>

      {profile.sources.length ? (
        <div className="border-t border-slate-200/70 pt-3">
          <SourceList sources={profile.sources} />
        </div>
      ) : null}
    </section>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-[11px] text-zinc-500">{label}</span>
      <span className="text-sm font-semibold tracking-tight text-ink">{children}</span>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (!items.length) return <span className="text-zinc-400">—</span>;
  return (
    <span className="flex flex-col gap-0.5">
      {items.map((t) => (
        <span key={t} className="tabular truncate text-[13px] font-medium" title={t}>
          {t}
        </span>
      ))}
    </span>
  );
}
