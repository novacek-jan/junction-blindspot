/** Pill chip from design/claude: sky = stages / never seen, mint = region / in CRM, plain = sectors. */
export function Chip({ tone, children, size = "md" }: { tone: "sky" | "mint" | "plain"; children: React.ReactNode; size?: "md" | "lg" }) {
  const cls =
    tone === "sky"
      ? "bg-sky-wash text-sky-ink font-semibold"
      : tone === "mint"
        ? "bg-mint-wash text-mint-ink font-semibold"
        : "border border-line bg-white text-muted font-medium";
  return <span className={`inline-flex items-center rounded-full text-sm ${size === "lg" ? "h-8 px-3.5" : "h-[30px] px-3"} ${cls}`}>{children}</span>;
}
