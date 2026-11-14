import type { Source } from "@/lib/types";
import { hostOf, safeUrl } from "@/lib/format";
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
  return /cala/i.test(s.name) || /cala\.ai/i.test(s.url ?? "");
}

function describe(s: Source) {
  return `${s.name}${s.rank ? ` · ${s.rank.toLowerCase()}` : ""}${safeUrl(s.url) ? ` — ${hostOf(s.url)}` : ""}`;
}

function Mark({ source, interactive }: { source: Source; interactive?: boolean }) {
  return (
    <span
      className={`inline-flex size-4 shrink-0 items-center justify-center rounded border text-[9px] font-bold leading-none ${rankClass(source.rank)} ${
        interactive ? "transition-colors hover:border-sky-400 hover:text-sky-700" : ""
      }`}
    >
      {isCala(source) ? "C" : <Icon name="link" className="size-3" />}
    </span>
  );
}

/** Single small source icon. Links out only for http(s) URLs; anything else renders as a plain mark. */
export function SourceIcon({ source }: { source: Source }) {
  const href = safeUrl(source.url);
  const label = describe(source);
  if (!href) {
    return (
      <span title={label} aria-label={`Source: ${label}`}>
        <Mark source={source} />
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      aria-label={`Source: ${label}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex"
    >
      <Mark source={source} interactive />
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

/** Labelled source list, e.g. a card footer. */
export function SourceList({ sources, label = "Sources" }: { sources: Source[]; label?: string }) {
  if (!sources?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-500">
      <span className="font-semibold uppercase tracking-wider">{label}</span>
      {sources.map((s, i) => {
        const href = safeUrl(s.url);
        const body = (
          <>
            <Mark source={s} />
            <span className="max-w-[16rem] truncate">{s.name}</span>
          </>
        );
        return href ? (
          <a
            key={`${s.url}-${i}`}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            title={describe(s)}
            className="inline-flex items-center gap-1 underline-offset-2 hover:text-sky-700 hover:underline"
          >
            {body}
          </a>
        ) : (
          <span key={`${s.url}-${i}`} title={describe(s)} className="inline-flex items-center gap-1">
            {body}
          </span>
        );
      })}
    </div>
  );
}
