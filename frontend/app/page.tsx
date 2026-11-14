"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { FundSearch } from "@/components/FundSearch";
import { ProfileCard } from "@/components/ProfileCard";
import { Icon } from "@/components/Icon";
import { ApiError, DEMO_FALLBACK, ERROR_MESSAGES, getDemoAudit, getFundProfile, previewCrm, runAudit, withTimeout } from "@/lib/api";
import { saveAudit } from "@/lib/auditStore";
import type { CrmField, CrmMapping, CrmPreview, FundProfile, FundSearchResult } from "@/lib/types";

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const CRM_FIELDS: { key: CrmField; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "website", label: "Website" },
  { key: "status", label: "Status" },
  { key: "date", label: "Date" },
];

export default function StartPage() {
  const router = useRouter();
  const [fund, setFund] = useState<FundSearchResult | null>(null);
  const [profile, setProfile] = useState<FundProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [csv, setCsv] = useState<File | null>(null);
  const [preview, setPreview] = useState<CrmPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const previewSeq = useRef(0);
  const codeRejected = useRef(false); // last preview failed with 401: retry once a new code is entered
  const [dragOver, setDragOver] = useState(false);
  // Demo and audit load independently: neither blocks the other's button.
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const demoSeq = useRef(0);
  const [auditLoading, setAuditLoading] = useState(false);
  const [error, setErrorState] = useState<{ message: string; offerDemo: boolean } | null>(null);
  // Access code for a real audit: React state only (never localStorage, sessionStorage or the URL).
  const [accessCode, setAccessCode] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const accessRef = useRef<HTMLInputElement>(null);

  function setError(e: unknown) {
    if (e == null) return setErrorState(null);
    if (typeof e === "string") return setErrorState({ message: e, offerDemo: false });
    if (e instanceof ApiError) return setErrorState({ message: e.message, offerDemo: DEMO_FALLBACK.has(e.kind) });
    setErrorState({ message: ERROR_MESSAGES.other, offerDemo: false });
  }

  async function selectFund(f: FundSearchResult) {
    setFund(f);
    setProfile(null);
    setError(null);
    setProfileLoading(true);
    try {
      const p = await getFundProfile(f.id);
      setProfile(p);
    } catch (e) {
      setError(e);
    } finally {
      setProfileLoading(false);
    }
  }

  function acceptFile(f: File | undefined) {
    if (!f) return;
    if (!/\.(csv|xlsx)$/i.test(f.name)) return setError(ERROR_MESSAGES.bad_format);
    if (f.size > MAX_FILE_BYTES) return setError(ERROR_MESSAGES.too_large);
    if (f.size === 0) return setError("That file is empty.");
    setError(null);
    setCsv(f);
    setPreview(null);
    void loadPreview(f, null);
  }

  // Reads the upload on the backend (no Cala calls) so the user can confirm the detected columns.
  async function loadPreview(file: File, mapping: CrmMapping | null) {
    const seq = ++previewSeq.current;
    codeRejected.current = false;
    setPreviewing(true);
    setError(null);
    try {
      const p = await previewCrm({ file, mapping, accessCode });
      if (seq === previewSeq.current) setPreview(p);
    } catch (e) {
      if (seq !== previewSeq.current) return;
      setPreview(null);
      setError(e);
      if (e instanceof ApiError && e.kind === "auth") {
        codeRejected.current = true;
        accessRef.current?.focus();
      }
    } finally {
      if (seq === previewSeq.current) setPreviewing(false);
    }
  }

  function changeMapping(field: CrmField, column: string) {
    if (!csv || !preview) return;
    void loadPreview(csv, { ...preview.mapping, [field]: column || null });
  }

  // Loads the demo here (15 s timeout) and only then opens Results, so a hang shows an error with Retry.
  async function startDemo() {
    const seq = ++demoSeq.current;
    setDemoLoading(true);
    setDemoError(null);
    try {
      const audit = await withTimeout(getDemoAudit());
      if (seq !== demoSeq.current) return;
      saveAudit(audit);
      router.push("/results");
    } catch (e) {
      if (seq !== demoSeq.current) return;
      setDemoError(e instanceof ApiError && e.kind === "timeout" ? "Demo didn't load: no response after 15 seconds." : "Demo didn't load: backend unavailable.");
      setDemoLoading(false);
    }
  }

  async function runRealAudit() {
    setAuditLoading(true);
    setError(null);
    try {
      const audit = await runAudit({ fundId: fund!.id, crmFile: csv!, mapping: preview?.mapping, accessCode });
      saveAudit(audit);
      router.push("/results");
    } catch (e) {
      setError(e);
      setAuditLoading(false);
      if (e instanceof ApiError && e.kind === "auth") accessRef.current?.focus();
    }
  }

  const canRun = !!fund && !!csv && !!preview && !previewing && !auditLoading;

  return (
    <AppShell crumb="New audit">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-9 px-4 py-12 sm:px-6 sm:py-14">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold tracking-tight">New audit</h1>
            <p className="text-sm text-zinc-600">Find the companies in your thesis that raised money and never hit your CRM.</p>
          </div>
          <button
            type="button"
            onClick={startDemo}
            disabled={demoLoading}
            className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-sky-200 bg-sky-100 px-4 text-sm font-semibold text-sky-700 shadow-sm transition-colors hover:border-sky-300 hover:bg-sky-200/70 disabled:opacity-60"
          >
            {demoLoading ? <Icon name="spinner" className="size-4 animate-spin" /> : <Icon name="sparkle" className="size-4" />}
            Try the demo
          </button>
        </div>

        {demoError ? (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800">
            {demoError}
            <button
              type="button"
              onClick={startDemo}
              disabled={demoLoading}
              className="h-8 rounded-lg border border-red-300 bg-white px-3 text-xs font-semibold text-red-800 hover:bg-red-100 disabled:opacity-60"
            >
              Retry
            </button>
          </div>
        ) : null}

        {/* 1. Fund */}
        <div className="flex flex-col gap-2">
          <Label>Fund</Label>
          <FundSearch selected={fund} onSelect={selectFund} autoFocus />
        </div>

        {profileLoading ? <ProfileSkeleton /> : profile ? <ProfileCard profile={profile} /> : null}

        {/* Access code: only part of the real-audit flow, never the demo */}
        {profile ? (
          <div className="animate-fade-in flex flex-col gap-2">
            <label htmlFor="access-code" className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Access code</span>
            </label>
            <input
              id="access-code"
              ref={accessRef}
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              onBlur={() => {
                // Retry reading the file once a code is entered after a 401.
                if (csv && codeRejected.current && !previewing && accessCode.trim()) void loadPreview(csv, null);
              }}
              className="h-10 w-full max-w-xs rounded-lg border border-slate-200 bg-white px-3 text-sm text-ink outline-none transition-all placeholder:text-slate-400 focus:border-ink focus:shadow-[0_0_0_2px_rgba(2,132,199,0.15)]"
            />
          </div>
        ) : null}

        {/* 3. CSV */}
        {profile ? (
          <div className="animate-fade-in flex flex-col gap-2">
            <Label>CRM export</Label>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                acceptFile(e.dataTransfer.files?.[0]);
              }}
              className={`group flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-9 text-center transition-all ${
                dragOver ? "border-sky-500 bg-sky-50" : csv ? "border-green-300 bg-green-50/50" : "border-slate-300 bg-white hover:border-ink hover:bg-slate-50"
              }`}
            >
              <span
                className={`flex size-9 items-center justify-center rounded-full transition-colors ${
                  csv ? "bg-green-100 text-green-700" : "bg-slate-50 text-ink group-hover:bg-sky-100"
                }`}
              >
                <Icon name={csv ? "check" : "upload"} className="size-[18px]" />
              </span>
              {csv ? (
                <span className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium text-ink">{csv.name}</span>
                  <span className="text-xs text-zinc-500">
                    {(csv.size / 1024).toFixed(1)} KB · <span className="text-sky-600 underline underline-offset-2">replace</span>
                  </span>
                </span>
              ) : (
                <span className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium text-ink">
                    Drop a .csv or .xlsx, or <span className="text-sky-600 underline underline-offset-2">browse</span>
                  </span>
                  <span className="text-xs text-zinc-500">Max 2 MB</span>
                </span>
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => {
                acceptFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            {previewing && !preview ? (
              <p className="flex items-center gap-2 text-xs text-zinc-500">
                <Icon name="spinner" className="size-3.5 animate-spin" /> Reading file…
              </p>
            ) : null}
            {preview ? <PreviewLine preview={preview} busy={previewing} onChange={changeMapping} /> : null}
          </div>
        ) : null}

        {error ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800">
            <span className="flex items-start gap-2">
              <Icon name="warning" className="mt-0.5 size-4 shrink-0" />
              {error.message}
            </span>
            {error.offerDemo ? (
              <button
                type="button"
                onClick={startDemo}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sky-200 bg-sky-100 px-3 text-xs font-semibold text-sky-700 hover:bg-sky-200/70"
              >
                <Icon name="sparkle" className="size-3.5" />
                Run the demo
              </button>
            ) : null}
          </div>
        ) : null}

        {profile ? (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              disabled={!canRun}
              onClick={runRealAudit}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-ink px-6 text-sm font-medium text-white shadow-sm transition-all hover:bg-ink-hover active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-zinc-300"
            >
              {auditLoading ? (
                <>
                  <Icon name="spinner" className="size-4 animate-spin" /> Running audit…
                </>
              ) : (
                <>
                  Run audit <Icon name="arrowRight" className="size-4" />
                </>
              )}
            </button>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

function PreviewLine({
  preview,
  busy,
  onChange,
}: {
  preview: CrmPreview;
  busy: boolean;
  onChange: (field: CrmField, column: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2" aria-busy={busy}>
      <p className="text-sm text-ink" role="status">
        We read {preview.row_count.toLocaleString("en-US")} companies
        {preview.matched_rows != null ? `, ${preview.matched_rows.toLocaleString("en-US")} matched in Cala` : ""}.
      </p>
      <div className="flex flex-wrap gap-2">
        {CRM_FIELDS.map(({ key, label }) => (
          <label key={key} className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            {label}
            <select
              value={preview.mapping[key] ?? ""}
              disabled={busy}
              onChange={(e) => onChange(key, e.target.value)}
              className="h-7 max-w-[11rem] rounded-md border border-slate-200 bg-white px-1.5 text-xs text-ink outline-none focus:border-ink disabled:opacity-60"
            >
              <option value="">—</option>
              {preview.columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">{children}</span>;
}

function ProfileSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4" aria-label="Loading fund profile">
      <div className="h-3 w-56 rounded bg-slate-200" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <div className="h-2.5 w-20 rounded bg-slate-200" />
            <div className="h-3.5 w-24 rounded bg-slate-200" />
          </div>
        ))}
      </div>
    </div>
  );
}
