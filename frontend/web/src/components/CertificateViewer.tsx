import { Check, X, AlertTriangle } from "lucide-react";
import type { Certificate, RiskConstraint } from "../types";

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function ConstraintRow({ constraint }: { constraint: RiskConstraint }) {
  const Icon = constraint.passed ? Check : constraint.hard ? X : AlertTriangle;
  const color = constraint.passed
    ? "text-aureum-success border-aureum-success/30 bg-aureum-success/10"
    : constraint.hard
    ? "text-aureum-danger border-aureum-danger/30 bg-aureum-danger/10"
    : "text-aureum-warning border-aureum-warning/30 bg-aureum-warning/10";

  return (
    <div className={`flex items-center justify-between p-3 rounded border ${color}`}>
      <div className="flex items-center gap-3">
        <Icon className="w-4 h-4" />
        <div>
          <p className="font-medium text-sm">{constraint.name.replace(/_/g, " ")}</p>
          <p className="text-xs opacity-80">
            limit {formatPct(constraint.limit)} {constraint.operator} actual{" "}
            {formatPct(constraint.actual)}
          </p>
        </div>
      </div>
      <span className="text-xs font-semibold uppercase">
        {constraint.passed ? "PASS" : constraint.hard ? "HARD FAIL" : "SOFT FAIL"}
      </span>
    </div>
  );
}

export default function CertificateViewer({
  certificate,
}: {
  certificate: Certificate | null;
}) {
  if (!certificate) {
    return (
      <div className="h-full flex items-center justify-center text-aureum-muted">
        Run a backtest to generate an Aureum Backtest Certificate.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-4 space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded bg-aureum-gold/10 flex items-center justify-center">
          <Check className="w-5 h-5 text-aureum-gold" />
        </div>
        <div>
          <h3 className="font-display text-lg font-semibold text-aureum-cream">
            Backtest Certificate
          </h3>
          <p className="text-xs text-aureum-muted">
            {certificate.generated_at} · v{certificate.aureum_version}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded bg-aureum-panel">
          <p className="text-xs text-aureum-muted uppercase">Total Return</p>
          <p className="font-mono text-lg text-aureum-cream">
            {formatPct(certificate.results.total_return)}
          </p>
        </div>
        <div className="p-3 rounded bg-aureum-panel">
          <p className="text-xs text-aureum-muted uppercase">Max Drawdown</p>
          <p className="font-mono text-lg text-aureum-cream">
            {formatPct(certificate.results.max_drawdown)}
          </p>
        </div>
        <div className="p-3 rounded bg-aureum-panel">
          <p className="text-xs text-aureum-muted uppercase">Volatility</p>
          <p className="font-mono text-lg text-aureum-cream">
            {formatPct(certificate.results.volatility_annual)}
          </p>
        </div>
        <div className="p-3 rounded bg-aureum-panel">
          <p className="text-xs text-aureum-muted uppercase">Sharpe</p>
          <p className="font-mono text-lg text-aureum-cream">
            {certificate.results.sharpe_ratio?.toFixed(2) ?? "—"}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-aureum-cream">Risk Constraints</h4>
        {certificate.risk_constraints.map((c) => (
          <ConstraintRow key={c.name} constraint={c} />
        ))}
      </div>

      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-aureum-cream">Input Lineage</h4>
        <div className="p-3 rounded bg-aureum-panel font-mono text-xs text-aureum-slate space-y-1">
          <p>Strategy: {certificate.inputs.strategy.sha256.slice(0, 16)}…</p>
          <p>Data: {certificate.inputs.data.sha256.slice(0, 16)}…</p>
        </div>
      </div>
    </div>
  );
}
