import Link from "next/link";

/** Top bar from design/claude: logo left, two pill links right. No sidebar. */
export function AppShell({ active, children }: { active: "new" | "audits"; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-page">
      <header className="mx-auto flex w-full max-w-[1240px] items-center justify-between gap-4 px-5 py-5 sm:px-10 sm:py-7 2xl:max-w-[1480px]">
        <Link href="/" className="flex items-center gap-2.5 text-ink no-underline">
          <Logo />
          <span className="font-display text-[21px] font-bold tracking-[-0.02em]">blindspot</span>
        </Link>
        <nav aria-label="Main" className="flex gap-1 sm:gap-2">
          <Pill href="/" on={active === "new"}>
            New audit
          </Pill>
          <Pill href="/results" on={active === "audits"}>
            Audits
          </Pill>
        </nav>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}

function Pill({ href, on, children }: { href: string; on: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={on ? "page" : undefined}
      className={`inline-flex h-11 items-center rounded-full px-4 text-[15px] no-underline transition-colors ${
        on ? "bg-ink font-semibold text-white hover:bg-ink-hover" : "font-medium text-muted hover:bg-chip hover:text-ink"
      }`}
    >
      {children}
    </Link>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
      <circle cx="15" cy="15" r="13" fill="#E3F7EA" />
      <path d="M15 2a13 13 0 0 1 0 26z" fill="#A9D6F7" />
      <circle cx="15" cy="15" r="4" fill="#0B1F33" />
    </svg>
  );
}
