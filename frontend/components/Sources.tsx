import type { Source } from "@/lib/types";
import { hostOf } from "@/lib/format";
import { Icon } from "./Icon";

const RANK_STYLE: Record<string, string> = {
  FILING: "bg-green-100 text-green-700 border-green-200",
  PRIMARY: "bg-sky-50 text-sky-700 border-sky-200",
  PRESS: "bg-zinc-100 text-zinc-600 border-zinc-200",
  AGGREGATOR: "bg-zinc-100 text-zinc-600 border-zinc-200",
};

function rankClass(rank: Source["rank"]) {
  return RANK_STYLE[rank ?? ""] ?? "bg-zinc-100 text-zinc-600 border-zinc-200";
}

function isCala(s: Source) {
  return /cala/i.test(s.name) || /cala\.ai/i.test(s.url);
}

/** Single small source icon-link (Cala sources get a "C" mark). */
export function SourceIcon({ source }: { source: Source }) {
  const label = `${source.name}${source.rank ? ` · ${source.rank.toLowerCase()}` : ""} — ${hostOf(source.url)}`;
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      aria-label={`Source: ${label}`}
      onClick={(e) => e.stopPropagation()}
      className={`inline-flex size-4 shrink-0 items-center justify-center rounded border text-[9px] font-bold leading-none transition-colors hover:border-sky-400 hover:text-sky-700 ${rankClass(source.rank)}`}
    >
      {isCala(source) ? "C" : <Icon name="link" className="size-3" />}
    </a>
  );
}

/** Row of source icons; collapses after `max`. */
export function SourceIcons({ sources, max = 3 }: { sources: Source[]; max?: number }) {
  if (!sources?.length) return null;
  const shown = sources.slice(0, max);
  return (
    <span className="inline-flex items-center gap-1">
      {shown.map((s, i) => (
        <SourceIcon key={`${s.url}-${i}`} source={s} />
      ))}
      {sources.length > max ? (
        <span className="font-mono text-[10px] text-zinc-500" title={sources.slice(max).map((s) => s.name).join(", ")}>
          +{sources.length - max}
        </span>
      ) : null}
    </span>
  );
}

/** Non-interactive mark, for use inside another link. */
function SourceMark({ source }: { source: Source }) {
  return (
    <span className={`inline-flex size-4 shrink-0 items-center justify-center rounded border text-[9px] font-bold leading-none ${rankClass(source.rank)}`}>
      {isCala(source) ? "C" : <Icon name="link" className="size-3" />}
    </span>
  );
}

/** Labelled source list, e.g. a card footer. */
export function SourceList({ sources, label = "Sources" }: { sources: Source[]; label?: string }) {
  if (!sources?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-500">
      <span className="font-semibold uppercase tracking-wider">{label}</span>
      {sources.map((s, i) => (
        <a
          key={`${s.url}-${i}`}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          title={`${s.name}${s.rank ? ` · ${s.rank.toLowerCase()}` : ""} — ${hostOf(s.url)}`}
          className="inline-flex items-center gap-1 underline-offset-2 hover:text-sky-700 hover:underline"
        >
          <SourceMark source={s} />
          <span className="max-w-[16rem] truncate">{s.name}</span>
        </a>
      ))}
    </div>
  );
}
