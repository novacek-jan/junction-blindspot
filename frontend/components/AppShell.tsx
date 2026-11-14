import Link from "next/link";
import { Icon } from "./Icon";
import { USE_MOCKS } from "@/lib/api";

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
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col justify-between border-r border-slate-200/80 bg-white px-4 py-5 lg:flex">
        <div className="flex flex-col gap-6">
          <Link href="/" className="flex items-center gap-2.5 px-3">
            <span className="flex size-7 items-center justify-center rounded-lg bg-ink text-sm font-bold text-white">B</span>
            <span className="text-base font-semibold tracking-tight">Blindspot</span>
          </Link>
          <nav>
            <Link
              href="/"
              aria-current="page"
              className="flex items-center gap-3 rounded-lg bg-ink px-3.5 py-2.5 text-sm font-medium text-white shadow-sm"
            >
              <Icon name="checkCircle" className="size-[18px]" />
              Audits
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-[11px] font-medium text-zinc-600">
          <span className="size-1.5 rounded-full bg-green-500" />
          {USE_MOCKS ? "Mock data" : "Data from Cala"}
        </div>
      </aside>

      <div className="flex min-h-screen flex-col lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-md sm:px-8">
          <div className="flex min-w-0 items-center gap-1.5 text-sm text-zinc-500">
            <Link href="/" className="flex items-center gap-2 transition-colors hover:text-ink">
              <span className="flex size-6 items-center justify-center rounded-md bg-ink text-xs font-bold text-white lg:hidden">B</span>
              Audits
            </Link>
            <Icon name="chevronRight" className="size-4 text-slate-400" />
            <span className="truncate font-semibold text-ink">{crumb}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">{right}</div>
        </header>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}

export function SimulatedCrmBadge() {
  return (
    <span
      title="Your pipeline was simulated from a demo CRM export, not your real CRM."
      className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800"
    >
      <span className="size-1.5 rounded-full bg-amber-500" />
      Simulated CRM
    </span>
  );
}

export function CalaBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-100 px-2.5 py-1 text-[11px] font-semibold text-green-700">
      <span className="size-1.5 rounded-full bg-green-400" />
      Verified by Cala
    </span>
  );
}
