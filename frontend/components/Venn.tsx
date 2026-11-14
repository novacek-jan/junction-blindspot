import type { Audit } from "@/lib/types";

/** Two overlapping circles: your pipeline vs. deals your peers closed. */
export function Venn({ venn }: { venn: Audit["venn"] }) {
  const pipeline = venn.pipeline_only + venn.overlap;
  const market = venn.overlap + venn.market_only;
  const maxR = 78;
  const minR = 44;
  const big = Math.max(pipeline, market, 1);
  const r = (n: number) => Math.max(minR, maxR * Math.sqrt(n / big));
  const rP = r(pipeline);
  const rM = r(market);
  const cy = 92;
  // Overlap depth grows with the share of the market you saw.
  const overlapShare = market ? venn.overlap / market : 0;
  const dist = rP + rM - Math.max(18, Math.min(rP, rM) * 2 * (0.2 + overlapShare * 0.6));
  const cxP = 160 - dist / 2;
  const cxM = 160 + dist / 2;
  const midX = (cxP + rP + (cxM - rM)) / 2;

  return (
    <figure className="flex flex-col items-center gap-2">
      <svg viewBox="0 0 320 196" className="w-full max-w-[320px]" role="img" aria-label={`Your pipeline ${pipeline} deals, peer deals ${market}, overlap ${venn.overlap}`}>
        <circle cx={cxP} cy={cy} r={rP} fill="rgba(74,222,128,0.15)" stroke="#4ade80" strokeWidth={1.5} />
        <circle cx={cxM} cy={cy} r={rM} fill="rgba(56,189,248,0.15)" stroke="#38bdf8" strokeWidth={1.5} />
        <Count x={(cxP - rP + (cxM - rM)) / 2} y={cy} value={venn.pipeline_only} color="#15803d" />
        <Count x={midX} y={cy} value={venn.overlap} color="#09090b" />
        <Count x={(cxP + rP + (cxM + rM)) / 2} y={cy} value={venn.market_only} color="#0284c7" big />
        <text x={cxP} y={cy + rP + 16} textAnchor="middle" className="fill-green-700 text-[10px] font-semibold uppercase tracking-wider">
          Your pipeline
        </text>
        <text x={cxM} y={cy + rM + 16} textAnchor="middle" className="fill-sky-700 text-[10px] font-semibold uppercase tracking-wider">
          Peer deals
        </text>
      </svg>
      <figcaption className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
        <Legend color="bg-green-400" label="Only in your pipeline" />
        <Legend color="bg-ink" label="Seen by you" />
        <Legend color="bg-sky-500" label="Never seen" />
      </figcaption>
    </figure>
  );
}

function Count({ x, y, value, color, big }: { x: number; y: number; value: number; color: string; big?: boolean }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      dominantBaseline="central"
      fill={color}
      className={`tabular font-mono font-bold ${big ? "text-[22px]" : "text-[16px]"}`}
    >
      {value}
    </text>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`size-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}
