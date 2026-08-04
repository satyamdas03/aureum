import { useState } from "react";
import { Play, Radio, AlertCircle, CheckCircle2, Download } from "lucide-react";
import { api } from "../api";
import type { LiveCertificate } from "../types";

interface LiveTradingPanelProps {
  strategyYaml: string;
  dataPath: string;
  disabled?: boolean;
}

function formatUSD(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export default function LiveTradingPanel({
  strategyYaml,
  dataPath,
  disabled,
}: LiveTradingPanelProps) {
  const [cert, setCert] = useState<LiveCertificate | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"check-only" | "dry-run">("dry-run");
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.live(strategyYaml, dataPath, {
        dry_run: mode === "dry-run",
        check_only: mode === "check-only",
        ignore_market_hours: true,
      });
      setCert(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Live run failed");
    } finally {
      setLoading(false);
    }
  };

  const account = cert?.pre_trade_account as Record<string, number> | undefined;
  const equity = account?.equity ?? 0;
  const hasErrors = cert?.errors && cert.errors.length > 0;

  return (
    <div className="bg-card border border-panel p-sm flex flex-col gap-md">
      <div className="flex items-center justify-between border-b border-card pb-sm">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-aureum-gold" />
          <span className="font-mono-label text-mono-label text-cream uppercase tracking-wider text-[10px]">
            Live Paper Trading
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <button
            onClick={() => setMode("check-only")}
            className={`px-2 py-1 rounded border ${
              mode === "check-only"
                ? "bg-aureum-gold text-deep-navy border-aureum-gold"
                : "border-card text-slate hover:border-outline-variant"
            }`}
          >
            Check only
          </button>
          <button
            onClick={() => setMode("dry-run")}
            className={`px-2 py-1 rounded border ${
              mode === "dry-run"
                ? "bg-aureum-gold text-deep-navy border-aureum-gold"
                : "border-card text-slate hover:border-outline-variant"
            }`}
          >
            Dry run
          </button>
        </div>
      </div>

      {!cert && (
        <div className="text-[11px] text-slate font-body-md leading-relaxed">
          Runs the current strategy against the live Alpaca paper account.
          <br />
          <span className="text-aureum-gold">Dry run</span> computes intended
          orders without submitting them.{" "}
          <span className="text-aureum-gold">Check only</span> validates the
          target portfolio and account state.
        </div>
      )}

      {cert && (
        <div className="flex flex-col gap-sm">
          <div className="flex items-center justify-between">
            <span className="font-mono-data text-[11px] text-cream">
              Mode: {cert.live_mode}
            </span>
            <span className="font-mono-data text-[10px] text-slate">
              {new Date(cert.generated_at).toLocaleString()}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-sm">
            <div className="bg-surface-container-high border border-card p-2">
              <div className="text-[10px] text-slate uppercase">Equity</div>
              <div className="font-mono-data text-cream">{formatUSD(equity)}</div>
            </div>
            <div className="bg-surface-container-high border border-card p-2">
              <div className="text-[10px] text-slate uppercase">Orders</div>
              <div className="font-mono-data text-cream">{cert.orders.length}</div>
            </div>
          </div>

          {hasErrors && (
            <div className="flex flex-col gap-1">
              {cert.errors.map((e, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-[11px] text-error bg-error-container/10 border border-error/20 p-2 rounded"
                >
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{e}</span>
                </div>
              ))}
            </div>
          )}

          {!hasErrors && cert.orders.length > 0 && (
            <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
              {cert.orders.map((o, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-[11px] font-mono-data border border-card bg-ink px-2 py-1"
                >
                  <span className="text-cream">
                    {o.side.toUpperCase()} {o.symbol}
                  </span>
                  <span className="text-slate">
                    {o.dry_run ? "dry-run" : o.status || "pending"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {!hasErrors && cert.orders.length === 0 && mode === "dry-run" && (
            <div className="flex items-center gap-2 text-[11px] text-slate">
              <CheckCircle2 className="w-4 h-4 text-aureum-gold" />
              No orders required.
            </div>
          )}

          <button
            onClick={() => {
              const blob = new Blob([JSON.stringify(cert, null, 2)], {
                type: "application/json",
              });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `live-${cert.run_id}.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="mt-1 inline-flex items-center justify-center gap-2 text-[10px] font-mono-label text-cream border border-card bg-ink hover:border-aureum-gold transition-colors py-1.5"
          >
            <Download className="w-3 h-3" />
            Download certificate
          </button>
        </div>
      )}

      {error && (
        <div className="text-[11px] text-error bg-error-container/10 border border-error/20 p-2 rounded">
          {error}
        </div>
      )}

      <button
        onClick={handleRun}
        disabled={disabled || loading}
        className="mt-auto bg-aureum-gold text-deep-navy font-mono-label text-mono-label font-bold py-md px-lg w-full flex items-center justify-center gap-sm hover:bg-primary transition-colors disabled:opacity-50"
      >
        {loading ? (
          <span className="w-4 h-4 border-2 border-deep-navy/30 border-t-deep-navy rounded-full animate-spin" />
        ) : (
          <Play className="w-4 h-4" />
        )}
        {mode === "check-only" ? "Check Live State" : "Run Dry-Run Live"}
      </button>
    </div>
  );
}
