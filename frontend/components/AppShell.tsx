import Link from "next/link";
import { Icon } from "./Icon";

export function AppShell({
  crumb,
  right,
  children,
}: {
  crumb: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-2 text-base text-zinc-700">
          <Link href="/" className="flex items-center gap-2 font-semibold text-zinc-950 hover:text-ink-hover">
            <span className="flex size-7 items-center justify-center rounded-md bg-ink text-sm font-bold text-white">B</span>
            Blindspot
          </Link>
          <Icon name="chevronRight" className="size-4 text-zinc-400" />
          <span className="truncate font-semibold text-zinc-950">{crumb}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">{right}</div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}

export function SimulatedCrmBadge() {
  return (
    <span
      title="Pipeline from a demo CRM export, not a real CRM."
      className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-900"
    >
      <span className="size-2 rounded-full bg-amber-500" />
      Simulated CRM
    </span>
  );
}
