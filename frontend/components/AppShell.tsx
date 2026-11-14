import Link from "next/link";
import { Icon } from "./Icon";

/** Layout from design/stitch/results_blindspot: fixed left sidebar (logo + Audits), sticky breadcrumb header. */
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
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col gap-6 border-r border-slate-200/80 bg-white px-4 py-6 lg:flex">
        <Link href="/" className="flex items-center gap-3 px-3">
          <Logo />
          <span className="text-lg font-bold tracking-tight text-ink">Blindspot</span>
        </Link>
        <nav className="flex flex-col gap-1">
          <Link href="/" aria-current="page" className="flex items-center gap-3 rounded-lg bg-ink px-3.5 py-2.5 text-base font-medium text-white shadow-sm hover:bg-black">
            <Icon name="checkCircle" className="size-5" />
            Audits
          </Link>
        </nav>
      </aside>
      <div className="flex min-h-screen flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-md sm:px-10">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-base text-zinc-600">
            <Link href="/" className="flex items-center gap-2 hover:text-ink">
              <span className="lg:hidden">
                <Logo />
              </span>
              Audits
            </Link>
            <Icon name="chevronRight" className="size-4 shrink-0 text-zinc-400" />
            <span className="truncate font-semibold text-ink">{crumb}</span>
          </nav>
          <div className="flex shrink-0 items-center gap-2">{right}</div>
        </header>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}

function Logo() {
  return <span className="flex size-8 items-center justify-center rounded-lg bg-ink text-base font-bold text-white">B</span>;
}

export function CalaBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-100 px-3 py-1 text-sm font-semibold text-green-700">
      <span className="size-2 rounded-full bg-green-400" />
      Data from Cala
    </span>
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
