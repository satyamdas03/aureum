import { Lock, Verified } from "lucide-react";

interface CertificateSealProps {
  strategyName?: string;
  strategyHash?: string;
  generatedAt?: string;
  passed?: boolean;
  className?: string;
  compact?: boolean;
}

function truncateHash(hash?: string): string {
  if (!hash) return "—";
  return `${hash.slice(0, 12)}…${hash.slice(-8)}`;
}

export default function CertificateSeal({
  strategyName,
  strategyHash,
  generatedAt,
  passed = true,
  className = "",
  compact = false,
}: CertificateSealProps) {
  if (compact) {
    return (
      <div
        className={`relative bg-card border border-aureum-gold p-md flex flex-col items-center justify-center text-center shadow-certificate ${className}`}
      >
        <div className="hash-mark-tl" />
        <div className="hash-mark-tr" />
        <div className="hash-mark-bl" />
        <div className="hash-mark-br" />
        <div className="w-12 h-12 rounded-full border border-aureum-gold flex items-center justify-center mb-md bg-ink">
          {passed ? (
            <Verified className="text-aureum-gold w-6 h-6" strokeWidth={1.5} />
          ) : (
            <Lock className="text-aureum-gold w-6 h-6" strokeWidth={1.5} />
          )}
        </div>
        <h3 className="font-mono-label text-mono-label text-aureum-gold tracking-widest uppercase mb-sm">
          {passed ? "Strategy Verified" : "Not Verified"}
        </h3>
        <p className="font-body-md text-[12px] text-slate mb-md">
          {strategyName || "Untitled Strategy"}
        </p>
        <div className="mt-auto w-full pt-sm border-t border-panel flex flex-col gap-1">
          <span className="font-mono-data text-[10px] text-outline-variant text-left">
            SHA-256 Checksum
          </span>
          <span className="font-mono-data text-[11px] text-slate truncate">
            {truncateHash(strategyHash)}
          </span>
          <span className="font-mono-data text-[10px] text-outline-variant text-right mt-1">
            TS: {generatedAt ? Math.floor(new Date(generatedAt).getTime() / 1000) : "—"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`relative bg-card border border-aureum-gold p-6 flex flex-col items-center justify-center text-center shadow-certificate ${className}`}
    >
      <div className="hash-mark-tl" />
      <div className="hash-mark-tr" />
      <div className="hash-mark-bl" />
      <div className="hash-mark-br" />
      <div className="w-12 h-12 rounded-full border border-aureum-gold flex items-center justify-center mb-md bg-ink">
        {passed ? (
          <Verified className="text-aureum-gold w-6 h-6" strokeWidth={1.5} />
        ) : (
          <Lock className="text-aureum-gold w-6 h-6" strokeWidth={1.5} />
        )}
      </div>
      <h3 className="font-mono-label text-mono-label text-aureum-gold tracking-widest uppercase mb-sm">
        {passed ? "Strategy Verified" : "Not Verified"}
      </h3>
      <p className="font-body-md text-[12px] text-slate mb-md">
        {passed
          ? "Syntax and logic parameters passed static analysis."
          : "One or more hard constraints failed verification."}
      </p>
      <div className="mt-auto w-full pt-sm border-t border-panel flex flex-col gap-1">
        <span className="font-mono-data text-[10px] text-outline-variant text-left">
          SHA-256 Checksum
        </span>
        <span className="font-mono-data text-[11px] text-slate truncate">
          {truncateHash(strategyHash)}
        </span>
        <span className="font-mono-data text-[10px] text-outline-variant text-right mt-1">
          TS: {generatedAt ? Math.floor(new Date(generatedAt).getTime() / 1000) : "—"}
        </span>
      </div>
    </div>
  );
}
