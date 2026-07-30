import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  Shield,
  Terminal,
  TrendingUp,
  Lock,
} from "lucide-react";
import PipelineHero from "./PipelineHero";
import CertificateSeal from "./CertificateSeal";

const features = [
  {
    icon: Terminal,
    title: "AI Author",
    description:
      "Describe a strategy in plain English. Aureum writes the YAML, validates it, and runs a dry-run backtest.",
  },
  {
    icon: TrendingUp,
    title: "Self-Proving Backtests",
    description:
      "Every run produces a content-addressed certificate with SHA-256 lineage, deterministic hashes, and risk constraints.",
  },
  {
    icon: Shield,
    title: "Reflection Loop",
    description:
      "When a hard constraint fails, Aureum asks the model to propose a fix, re-runs the backtest, and saves numbered drafts.",
  },
];

const checks = [
  "Natural language → validated strategy YAML",
  "Built-in signals: momentum, volatility, Sharpe, mean-reversion",
  "Dimensional type system catches unit errors",
  "SMT-LIB and Lean 4 verifier bridge",
  "Alpaca real-market snapshot adapter",
];

const sampleSeal = {
  strategyName: "low-vol-quality",
  strategyHash: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa5d0fbcf0d5a3d8e7b0f7e9a",
  dataHash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  generatedAt: new Date().toISOString(),
  version: "0.3.0",
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-aureum-ink">
      {/* Nav */}
      <nav className="border-b border-aureum-panel">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-aureum-gold flex items-center justify-center">
              <span className="font-display font-bold text-aureum-ink text-lg">
                A
              </span>
            </div>
            <span className="font-display text-xl font-semibold text-aureum-cream">
              Aureum
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              to="/pricing"
              className="hidden sm:inline-flex px-3 py-2 text-sm font-medium text-aureum-slate hover:text-aureum-cream transition-colors"
            >
              Pricing
            </Link>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-aureum-ink bg-aureum-gold hover:bg-aureum-gold-soft transition-colors rounded"
            >
              Open Dashboard
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-aureum-gold/5 via-transparent to-transparent" />
        <div className="relative max-w-7xl mx-auto px-6 pt-20 pb-16 md:pt-28 md:pb-20">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="text-center lg:text-left">
              <p className="inline-block px-3 py-1 mb-6 text-xs font-semibold tracking-wider uppercase text-aureum-gold border border-aureum-gold/30 rounded-full">
                v0.3.0 — Now with Claude-powered authoring
              </p>
              <h1 className="font-display text-5xl md:text-6xl lg:text-7xl font-bold text-aureum-cream leading-[1.05] tracking-tight">
                The self-proving semantic kernel for finance
              </h1>
              <p className="mt-6 text-lg md:text-xl text-aureum-slate max-w-xl mx-auto lg:mx-0">
                Write financial logic. Prove it correct. Run it anywhere. Aureum
                turns quant strategies into auditable, self-proving backtest
                certificates.
              </p>

              <div className="mt-10 flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-4">
                <Link
                  to="/dashboard"
                  className="inline-flex items-center gap-2 px-6 py-3 text-base font-semibold text-aureum-ink bg-aureum-gold hover:bg-aureum-gold-soft transition-colors rounded"
                >
                  Try the dashboard
                  <ArrowRight className="w-5 h-5" />
                </Link>
                <a
                  href="https://github.com/satyamdas03/aureum"
                  className="inline-flex items-center gap-2 px-6 py-3 text-base font-medium text-aureum-cream border border-aureum-muted hover:border-aureum-gold transition-colors rounded"
                >
                  View on GitHub
                </a>
              </div>
            </div>

            <div className="relative">
              <div className="absolute inset-0 bg-aureum-gold/5 blur-3xl rounded-full" />
              <CertificateSeal {...sampleSeal} passed />
            </div>
          </div>

          <div className="mt-20">
            <PipelineHero />
          </div>
        </div>
      </section>

      {/* Trust strip */}
      <section className="border-t border-aureum-panel bg-aureum-panel/30">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="flex flex-wrap items-center justify-center gap-8 text-aureum-muted text-sm">
            <div className="flex items-center gap-2">
              <Lock className="w-4 h-4 text-aureum-gold" />
              <span>SHA-256 lineage</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-aureum-gold" />
              <span>Deterministic replay</span>
            </div>
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-aureum-gold" />
              <span>Hard-constraint enforcement</span>
            </div>
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-aureum-gold" />
              <span>Open source Apache-2.0</span>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-aureum-panel">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <p className="text-center text-xs font-semibold tracking-[0.15em] uppercase text-aureum-gold mb-4">
            Capabilities
          </p>
          <h2 className="font-display text-3xl md:text-4xl font-bold text-aureum-cream text-center mb-16 max-w-2xl mx-auto">
            From plain English to a verified certificate
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="p-6 rounded-lg bg-aureum-card border border-aureum-panel hover:border-aureum-gold/30 transition-colors"
                >
                  <div className="w-10 h-10 rounded bg-aureum-gold/10 flex items-center justify-center mb-4">
                    <Icon className="w-5 h-5 text-aureum-gold" />
                  </div>
                  <h3 className="font-display text-xl font-semibold text-aureum-cream mb-2">
                    {feature.title}
                  </h3>
                  <p className="text-aureum-slate text-sm leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="border-t border-aureum-panel bg-aureum-panel/30">
        <div className="max-w-7xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-xs font-semibold tracking-[0.15em] uppercase text-aureum-gold mb-4">
              Why Aureum
            </p>
            <h2 className="font-display text-3xl md:text-4xl font-bold text-aureum-cream mb-4">
              From idea to auditable certificate
            </h2>
            <p className="text-aureum-slate mb-8">
              Aureum is not another backtester. It is a formal financial
              operating substrate: every strategy, every data source, and every
              result is versioned, hashed, and checked against hard
              constraints.
            </p>
            <ul className="space-y-4">
              {checks.map((check) => (
                <li key={check} className="flex items-start gap-3">
                  <div className="mt-0.5 w-5 h-5 rounded-full bg-aureum-gold/10 flex items-center justify-center shrink-0">
                    <Check className="w-3 h-3 text-aureum-gold" />
                  </div>
                  <span className="text-aureum-cream">{check}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-lg border border-aureum-panel bg-aureum-ink p-6 font-mono text-sm">
            <div className="flex items-center gap-2 mb-4 text-aureum-muted">
              <span className="w-3 h-3 rounded-full bg-aureum-danger" />
              <span className="w-3 h-3 rounded-full bg-aureum-warning" />
              <span className="w-3 h-3 rounded-full bg-aureum-success" />
              <span className="ml-2">strat_001.yaml</span>
            </div>
            <pre className="text-aureum-slate leading-relaxed">
{`apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: low-vol-quality
spec:
  ranking:
    by: sharpe_63d
    ascending: false
  risk:
    max_drawdown:
      value: 0.20
      hard: true`}
            </pre>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-aureum-panel">
        <div className="max-w-7xl mx-auto px-6 py-24 text-center">
          <h2 className="font-display text-3xl md:text-4xl font-bold text-aureum-cream mb-4">
            Start proving your strategies
          </h2>
          <p className="text-aureum-slate max-w-xl mx-auto mb-8">
            Open Aureum Studio, describe a strategy in plain English, and get a
            self-proving backtest certificate in seconds.
          </p>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 px-6 py-3 text-base font-semibold text-aureum-ink bg-aureum-gold hover:bg-aureum-gold-soft transition-colors rounded"
          >
            Open Aureum Studio
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-aureum-panel bg-aureum-panel/30">
        <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-aureum-muted text-sm">
            © {new Date().getFullYear()} Aureum. Open source under Apache-2.0.
          </p>
          <div className="flex items-center gap-6">
            <Link
              to="/pricing"
              className="text-aureum-muted hover:text-aureum-cream text-sm transition-colors"
            >
              Pricing
            </Link>
            <a
              href="https://github.com/satyamdas03/aureum/releases/tag/v0.3.0"
              className="text-aureum-gold hover:text-aureum-gold-soft text-sm"
            >
              v0.3.0 release →
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
