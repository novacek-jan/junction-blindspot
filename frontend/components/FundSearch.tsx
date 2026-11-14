"use client";

import { useEffect, useId, useRef, useState } from "react";
import { searchFunds } from "@/lib/api";
import type { FundSearchResult } from "@/lib/types";
import { Icon } from "./Icon";

export function FundSearch({
  id,
  selected,
  onSelect,
  placeholder = "Search your fund, e.g. Lifeline Ventures",
  excludeIds = [],
  compact = false,
  autoFocus = false,
}: {
  id?: string;
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
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, searchable, excludeIds.join(",")]);

  // Keep the active option visible when moving through a long list with the arrow keys.
  useEffect(() => {
    document.getElementById(listId)?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active, listId]);

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
        <Icon name="search" className="pointer-events-none absolute left-[18px] size-[18px] text-muted group-focus-within:text-ink" />
        <input
          id={id}
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
          className={`w-full rounded-[14px] border-[1.5px] bg-white pl-12 pr-11 font-semibold text-ink outline-none transition-colors placeholder:font-normal placeholder:text-faint focus:border-ink focus:shadow-[0_0_0_3px_rgba(90,174,234,0.25)] ${
            compact ? "h-10 text-sm" : "h-14 text-lg"
          } ${isSelected ? "border-ink" : "border-field"}`}
        />
        <span className="pointer-events-none absolute right-4 flex items-center">
          {loading && searchable ? (
            <Icon name="spinner" className="size-4 animate-spin text-faint" />
          ) : isSelected ? (
            <Icon name="checkCircle" className="size-5 text-mint-ink" />
          ) : null}
        </span>
      </div>
      {open && shown.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-2 max-h-80 w-full overflow-auto rounded-[14px] border border-line bg-white p-1.5 shadow-[var(--shadow-overlay)]"
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
              className={`flex cursor-pointer items-center justify-between gap-3 rounded-[10px] px-3.5 py-2.5 text-base ${
                i === active ? "bg-ice text-ink" : "text-ink"
              }`}
            >
              <span className="font-semibold">{f.name}</span>
              <span className="flex shrink-0 items-center gap-2 text-sm text-muted">
                {f.basis_rounds != null ? <span className="tabular">based on {f.basis_rounds} rounds</span> : null}
                <Icon name="arrowRight" className={`size-4 text-faint ${i === active ? "" : "invisible"}`} />
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
