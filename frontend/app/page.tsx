"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { FundSearch } from "@/components/FundSearch";
import { Chip } from "@/components/Chip";
import { Icon } from "@/components/Icon";
import { ApiError, ERROR_MESSAGES, getFundProfile, previewCrm, runAudit } from "@/lib/api";
import { saveUploadedAudit } from "@/lib/auditStore";
import { regionLabel, sectorLabel, stageRange } from "@/lib/present";
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
  const [auditLoading, setAuditLoading] = useState(false);
  const [error, setErrorState] = useState<{ message: string } | null>(null);
  // Access code for a real audit: React state only (never localStorage, sessionStorage or the URL).
  const [accessCode, setAccessCode] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const accessRef = useRef<HTMLInputElement>(null);

  function setError(e: unknown) {
    if (e == null) return setErrorState(null);
    if (typeof e === "string") return setErrorState({ message: e });
    if (e instanceof ApiError) return setErrorState({ message: e.message });
    setErrorState({ message: ERROR_MESSAGES.other });
  }

  async function selectFund(f: FundSearchResult) {
    setFund(f);
    setProfile(null);
    setError(null);
    setProfileLoading(true);
    try {
      setProfile(await getFundProfile(f.id));
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

  async function runRealAudit() {
    setAuditLoading(true);
    setError(null);
    try {
      const audit = await runAudit({ fundId: fund!.id, crmFile: csv!, mapping: preview?.mapping, accessCode });
      saveUploadedAudit(audit);
      router.push("/results");
    } catch (e) {
      setError(e);
      setAuditLoading(false);
      if (e instanceof ApiError && e.kind === "auth") accessRef.current?.focus();
    }
  }

  const canRun = !!fund && !!csv && !!preview && !previewing && !auditLoading;

  return (
    <AppShell active="new">
      <div className="mx-auto flex w-full max-w-[1240px] flex-wrap items-start gap-10 px-5 pb-16 pt-4 sm:gap-14 sm:px-10 sm:pb-[72px] sm:pt-8 2xl:max-w-[1480px]">
        {/* Left: pitch */}
        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-7 pt-2 sm:pt-6">
          <h1 className="font-display text-[44px] font-bold leading-[1.02] tracking-[-0.04em] sm:text-[64px] 2xl:text-[72px]">
            See the deals your CRM <span className="marker">never saw.</span>
          </h1>
          <p className="max-w-[500px] text-lg leading-relaxed text-muted sm:text-[19px] 2xl:max-w-[560px] 2xl:text-xl">
            We rebuild your thesis from your own rounds, map every VC-backed company in it that raised since 2022, and show the ones that never reached your pipeline.
          </p>
          <DotGrid />
          <div className="flex gap-5 text-sm text-muted">
            <span className="inline-flex items-center gap-2">
              <span className="size-3 rounded-full bg-mint-mid" />
              In your CRM
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="size-3 rounded-full bg-sky-dot" />
              Never seen
            </span>
          </div>
        </div>

        {/* Right: the audit form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canRun) void runRealAudit();
          }}
          className="flex min-w-0 flex-[1_1_460px] flex-col gap-7 rounded-3xl border border-line bg-white p-6 shadow-card sm:p-8"
        >
          <section className="flex flex-col gap-3.5">
            <Step n="01">
              <label htmlFor="fund-search">Your fund</label>
            </Step>
            <FundSearch id="fund-search" selected={fund} onSelect={selectFund} autoFocus />
            {profileLoading ? <ThesisSkeleton /> : profile ? <ThesisSummary profile={profile} /> : null}
          </section>

          <section className="flex flex-col gap-3.5">
            <Step n="02">
              <h2>Your CRM export</h2>
            </Step>
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
              className={`flex flex-col items-center gap-2.5 rounded-2xl border-[1.5px] border-dashed px-5 py-8 text-center transition-colors ${
                dragOver ? "border-sky-dot bg-sky-wash" : csv ? "border-mint-mid bg-mint-wash/50" : "border-[#A9C7DF] bg-[#FBFDFF] hover:border-sky-dot hover:bg-ice"
              }`}
            >
              <span className={`flex size-[52px] items-center justify-center rounded-full ${csv ? "bg-mint-wash text-mint-ink" : "bg-sky-wash text-link"}`}>
                {csv ? <Icon name="check" className="size-6" /> : <UploadIcon />}
              </span>
              {csv ? (
                <>
                  <span className="text-[17px] font-semibold text-ink">{csv.name}</span>
                  <span className="text-sm text-muted">
                    {(csv.size / 1024).toFixed(1)} KB · <span className="text-link underline">replace</span>
                  </span>
                </>
              ) : (
                <>
                  <span className="text-[17px] font-semibold text-ink">
                    Drop a .csv or .xlsx, or <span className="text-link underline">browse</span>
                  </span>
                  <span className="text-sm text-muted">Affinity, HubSpot, Pipedrive, Attio or any sheet with company names · max 2 MB</span>
                </>
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
              <p className="flex items-center gap-2 text-sm text-muted">
                <Icon name="spinner" className="size-4 animate-spin" /> Reading file…
              </p>
            ) : null}
            {preview ? <PreviewLine preview={preview} busy={previewing} onChange={changeMapping} /> : null}

            <div className="flex flex-col gap-1.5">
              <label htmlFor="access-code" className="text-sm font-semibold text-muted">
                Access code
              </label>
              <input
                id="access-code"
                ref={accessRef}
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder="From the Blindspot team"
                value={accessCode}
                onChange={(e) => setAccessCode(e.target.value)}
                onBlur={() => {
                  // Retry reading the file once a code is entered after a 401.
                  if (csv && codeRejected.current && !previewing && accessCode.trim()) void loadPreview(csv, null);
                }}
                className="h-[50px] rounded-xl border border-field bg-white px-4 text-base text-ink outline-none transition-colors placeholder:text-faint focus:border-ink focus:shadow-[0_0_0_3px_rgba(90,174,234,0.25)]"
              />
            </div>
          </section>

          {error ? (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[15px] text-red-800">
              <span className="flex items-start gap-2">
                <Icon name="warning" className="mt-0.5 size-4 shrink-0" />
                {error.message}
              </span>
            </div>
          ) : null}

          <div className="flex flex-col gap-3.5">
            <button
              type="submit"
              disabled={!canRun}
              className="flex h-14 items-center justify-center gap-2.5 rounded-[14px] bg-ink font-display text-lg font-semibold text-white transition-colors hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-35"
            >
              {auditLoading ? (
                <>
                  <Icon name="spinner" className="size-5 animate-spin" /> Running audit…
                </>
              ) : (
                <>
                  Run audit <ArrowIcon />
                </>
              )}
            </button>
            <p className="flex items-center justify-center gap-2 text-center text-sm text-muted">
              <LockIcon />
              Your CRM rows never reach an AI model.
            </p>
          </div>
        </form>
      </div>
    </AppShell>
  );
}

function Step({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2.5 font-display">
      <span className="text-[15px] font-bold text-sky-num">{n}</span>
      <span className="text-[22px] font-semibold tracking-[-0.02em] [&>*]:m-0 [&>*]:text-inherit [&>*]:font-inherit">{children}</span>
    </div>
  );
}

// "Thesis from 12 own rounds since 2022" + stage range, region and sector chips, from the fund profile.
function ThesisSummary({ profile }: { profile: FundProfile }) {
  const t = profile.thesis;
  const stages = stageRange(t?.stages ?? profile.stages.map((s) => s.label));
  const region = regionLabel(t?.countries ?? profile.countries.map((c) => c.name));
  const sectors = sectorLabel(t?.industries ?? profile.industries.map((i) => ({ code: "", name: i.name })), 3);
  return (
    <div className="animate-fade-in flex flex-col gap-2.5 rounded-[14px] bg-ice px-[18px] py-4">
      <span className="text-sm text-muted">
        Thesis from <strong className="font-semibold text-ink">{profile.investments_since_2022} own rounds</strong> since 2022
      </span>
      <div className="flex flex-wrap gap-1.5">
        {stages ? <Chip tone="sky">{stages}</Chip> : null}
        {region ? <Chip tone="mint">{region}</Chip> : null}
        {sectors ? <Chip tone="plain">{sectors}</Chip> : null}
      </div>
    </div>
  );
}

function ThesisSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-2.5 rounded-[14px] bg-ice px-[18px] py-4" aria-label="Loading fund thesis">
      <div className="h-3.5 w-48 rounded bg-line" />
      <div className="flex gap-1.5">
        <div className="h-[30px] w-36 rounded-full bg-line" />
        <div className="h-[30px] w-20 rounded-full bg-line" />
        <div className="h-[30px] w-44 rounded-full bg-line" />
      </div>
    </div>
  );
}

function PreviewLine({ preview, busy, onChange }: { preview: CrmPreview; busy: boolean; onChange: (field: CrmField, column: string) => void }) {
  return (
    <div className="flex flex-col gap-2" aria-busy={busy}>
      <p className="text-[15px] text-ink" role="status">
        We read {preview.row_count.toLocaleString("en-US")} companies
        {preview.matched_rows != null ? `, ${preview.matched_rows.toLocaleString("en-US")} matched in Cala` : ""}.
      </p>
      <div className="flex flex-wrap gap-2">
        {CRM_FIELDS.map(({ key, label }) => (
          <label key={key} className="flex items-center gap-1.5 text-xs font-medium text-muted">
            {label}
            <select
              value={preview.mapping[key] ?? ""}
              disabled={busy}
              onChange={(e) => onChange(key, e.target.value)}
              className="h-8 max-w-[11rem] rounded-lg border border-field bg-white px-2 text-sm text-ink outline-none focus:border-ink disabled:opacity-60"
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

// Decorative: 36 dots, 14 of them "never seen". Not data.
const BLIND_DOTS = new Set([2, 5, 7, 11, 14, 15, 19, 22, 24, 27, 28, 31, 33, 34]);
function DotGrid() {
  return (
    <div aria-hidden="true" className="grid w-fit grid-cols-[repeat(12,16px)] gap-2 pt-2 sm:grid-cols-[repeat(12,22px)] sm:gap-2.5">
      {Array.from({ length: 36 }, (_, i) => (
        <span key={i} className={`aspect-square rounded-full ${BLIND_DOTS.has(i) ? "bg-sky-dot" : "bg-mint-mid"}`} />
      ))}
    </div>
  );
}

function UploadIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 16V5M7 10l5-5 5 5" />
      <path d="M5 19h14" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#1F6B3B" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}
