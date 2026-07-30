import { Check, Lock } from "lucide-react";

interface CertificateSealProps {
  strategyName?: string;
  strategyHash?: string;
  dataHash?: string;
  generatedAt?: string;
  version?: string;
  passed?: boolean;
  className?: string;
}

function truncateHash(hash?: string): string {
  if (!hash) return "—";
  return `${hash.slice(0, 12)}…${hash.slice(-8)}`;
}

export default function CertificateSeal({
  strategyName,
  strategyHash,
  dataHash,
  generatedAt,
  version,
  passed = true,
  className = "",
}: CertificateSealProps) {
  return (
    <div className={`relative p-6 bg-aureum-card border border-aureum-gold/40 rounded-lg overflow-hidden ${className}`}>
      {/* Corner hash marks */}
      <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-aureum-gold/60" />
      <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-aureum-gold/60" />
      <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-aureum-gold/60" />
      <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-aureum-gold/60" />

      {/* Top gold accent bar */}
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-aureum-gold" />

      <div className="relative flex items-start gap-4">
        <div className="shrink-0 w-14 h-14 rounded-full bg-aureum-gold/10 border border-aureum-gold/40 flex items-center justify-center">
          {passed ? (
            <Check className="w-7 h-7 text-aureum-gold" strokeWidth={2.5} />
          ) : (
            <Lock className="w-7 h-7 text-aureum-gold" strokeWidth={2} />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-aureum-gold mb-1">
            Aureum Backtest Certificate
          </p>
          <h3 className="font-display text-xl font-semibold text-aureum-cream truncate">
            {strategyName || "Untitled Strategy"}
          </h3>

          <div className="mt-4 space-y-2 font-mono text-xs text-aureum-slate">
            <div className="flex items-center gap-2">
              <span className="text-aureum-muted w-20 shrink-0">Strategy</span>
              <span className="truncate">{truncateHash(strategyHash)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-aureum-muted w-20 shrink-0">Data</span>
              <span className="truncate">{truncateHash(dataHash)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-aureum-muted w-20 shrink-0">Generated</span>
              <span>{generatedAt ? new Date(generatedAt).toLocaleString() : "—"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-aureum-muted w-20 shrink-0">Version</span>
              <span>{version || "—"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Status footer */}
      <div className="relative mt-5 pt-4 border-t border-aureum-gold/20 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-aureum-gold">
          {passed ? "Verified" : "Not verified"}
        </span>
        <span className="font-mono text-[10px] text-aureum-muted">
          SHA-256 content-addressed
        </span>
      </div>
    </div>
  );
}
