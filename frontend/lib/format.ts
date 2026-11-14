const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", USD: "$", GBP: "£" };

export function formatAmount(amount: number | null | undefined, currency: string): string {
  if (amount == null || !Number.isFinite(amount)) return "—";
  const abs = Math.abs(amount);
  const short =
    abs >= 1e9 ? `${trim(amount / 1e9)}B` : abs >= 1e6 ? `${trim(amount / 1e6)}M` : abs >= 1e3 ? `${trim(amount / 1e3)}k` : `${amount}`;
  const sym = CURRENCY_SYMBOL[currency];
  return sym ? `${sym}${short}` : `${short} ${currency}`;
}

function trim(n: number) {
  return n >= 100 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "");
}

export function stageLabel(code: string): string {
  return code
    .toLowerCase()
    .split("_")
    .map((w) => (w.length === 1 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ")
    .replace("Pre Seed", "Pre-Seed");
}

/** Newest first; missing dates (the backend sends null for some grant rounds) sort last. */
export function byDateDesc(a: { date: string | null }, b: { date: string | null }): number {
  return (b.date ?? "").localeCompare(a.date ?? "");
}

export function formatDate(iso: string | null, withDay = false): string {
  if (!iso) return "Date unknown";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    ...(withDay ? { day: "numeric" } : {}),
    timeZone: "UTC",
  });
}

export function pct(share: number) {
  return `${Math.round(share * 100)}%`;
}

export function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Returns the URL only if it is http(s); blocks javascript:, data:, etc. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

/** Company websites arrive as bare domains ("vayu-robotics.se"); normalise to https. */
export function websiteUrl(website: string | null | undefined): string | null {
  if (!website) return null;
  return safeUrl(/^[a-z][a-z0-9+.-]*:/i.test(website) ? website : `https://${website}`);
}
