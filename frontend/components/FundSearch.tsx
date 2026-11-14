"use client";

import { useEffect, useId, useRef, useState } from "react";
import { searchFunds } from "@/lib/api";
import type { FundSearchResult } from "@/lib/types";
import { Icon } from "./Icon";

export function FundSearch({
  selected,
  onSelect,
  placeholder = "Search your fund, e.g. Point Nine…",
  excludeIds = [],
  compact = false,
  autoFocus = false,
}: {
  selected?: FundSearchResult | null;
  onSelect: (fund: FundSearchResult) => void;
  placeholder?: string;
  excludeIds?: string[];
  compact?: boolean;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState(selected?.name ?? "");
  const [results, setResults] = useState<FundSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const listId = useId();
  const boxRef = useRef<HTMLDivElement>(null);

  const q = query.trim();
  const searchable = q.length >= 2 && !(selected && q === selected.name);
  const shown = searchable ? results : [];

  useEffect(() => {
    if (!searchable) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setLoading(true);
      searchFunds(q)
        .then((r) => {
          if (cancelled) return;
          setResults(r.filter((f) => !excludeIds.includes(f.id)));
          setActive(0);
        })
        .catch(() => !cancelled && setResults([]))
        .finally(() => !cancelled && setLoading(false));
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, searchable, excludeIds.join(",")]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const choose = (f: FundSearchResult) => {
    onSelect(f);
    setQuery(compact ? "" : f.name);
    setOpen(false);
    setResults([]);
  };

  const isSelected = !!selected && query === selected.name;

  return (
    <div ref={boxRef} className="relative">
      <div className="group relative flex items-center">
        <Icon name="search" className="pointer-events-none absolute left-3.5 size-[18px] text-slate-400 group-focus-within:text-ink" />
        <input
          role="combobox"
          aria-expanded={open && shown.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          autoFocus={autoFocus}
          value={query}
          placeholder={placeholder}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (!shown.length) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => (a + 1) % shown.length);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => (a - 1 + shown.length) % shown.length);
            } else if (e.key === "Enter") {
              e.preventDefault();
              choose(shown[active]);
            } else if (e.key === "Escape") setOpen(false);
          }}
          className={`w-full rounded-lg border border-slate-200 bg-white pl-10 pr-10 font-medium text-ink outline-none transition-all placeholder:font-normal placeholder:text-slate-400 focus:border-ink focus:shadow-[0_0_0_2px_rgba(2,132,199,0.15)] ${
            compact ? "h-9 text-xs" : "h-12 text-sm"
          }`}
        />
        <span className="pointer-events-none absolute right-3 flex items-center">
          {loading && searchable ? (
            <Icon name="spinner" className="size-4 animate-spin text-slate-400" />
          ) : isSelected ? (
            <Icon name="checkCircle" className="size-[18px] text-green-600" />
          ) : null}
        </span>
      </div>
      {open && shown.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1.5 max-h-72 w-full overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-[var(--shadow-overlay)]"
        >
          {shown.map((f, i) => (
            <li
              key={f.id}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(f);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center justify-between rounded-md px-3 py-2 text-sm ${
                i === active ? "bg-slate-100 text-ink" : "text-zinc-700"
              }`}
            >
              <span className="font-medium">{f.name}</span>
              {i === active ? <Icon name="arrowRight" className="size-3.5 text-zinc-400" /> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
