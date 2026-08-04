import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Play,
  Sparkles,
  RotateCcw,
  Code,
  Save,
  AlignLeft,
  ShieldCheck,
  LayoutDashboard as DashboardIcon,
  GitBranch as AccountTreeIcon,
  BarChart,
  Settings,
  Bell,
  Activity,
  Plus,
} from "lucide-react";
import { api } from "../api";
import type { Certificate, DataFile, Example } from "../types";
import StrategyEditor from "./StrategyEditor";
import CertificateSeal from "./CertificateSeal";
import BacktestChart from "./BacktestChart";
import Phase4Lineage from "./Phase4Lineage";
import LiveTradingPanel from "./LiveTradingPanel";

const DEFAULT_STRATEGY = `apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: my-strategy
  description: Describe your strategy here.
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.00
      min_adv20: 1000000
  schedule:
    rebalance: 1M
    lookback: 252d
  ranking:
    by: momentum_12_1
    ascending: false
  weights:
    kind: equal
    top_n: 0.20
  execution:
    slippage: 0.0005
  risk:
    max_drawdown:
      value: 0.30
      hard: true
    max_leverage:
      value: 1.50
      hard: true
    max_turnover_annual:
      value: 20.00
      hard: false
    max_concentration_single_name:
      value: 0.30
      hard: true
`;

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

const navItems = [
  { icon: DashboardIcon, label: "Dashboard", active: true },
  { icon: Code, label: "Editor", active: false },
  { icon: AccountTreeIcon, label: "Models", active: false },
  { icon: BarChart, label: "Backtests", active: false },
  { icon: Settings, label: "Settings", active: false },
];

export default function Dashboard() {
  const [yaml, setYaml] = useState(DEFAULT_STRATEGY);
  const [prompt, setPrompt] = useState("");
  const [dataPath, setDataPath] = useState("examples/data/synthetic_prices.csv");
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [signals, setSignals] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<"" | "author" | "backtest" | "reflect">("");
  const [error, setError] = useState<string | null>(null);
  const [activeEnv, setActiveEnv] = useState<"Mainnet" | "Staging">("Mainnet");

  useEffect(() => {
    api.examples().then(setExamples).catch(() => setExamples([]));
    api.data().then(setDataFiles).catch(() => setDataFiles([]));
    api.signals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const handleAuthor = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setAction("author");
    setError(null);
    try {
      const result = await api.author(prompt);
      setYaml(result.yaml);
      setCertificate(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Author failed");
    } finally {
      setLoading(false);
      setAction("");
    }
  };

  const handleBacktest = async () => {
    setLoading(true);
    setAction("backtest");
    setError(null);
    try {
      const cert = await api.backtest(yaml, dataPath);
      setCertificate(cert);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
      setAction("");
    }
  };

  const handleReflect = async () => {
    setLoading(true);
    setAction("reflect");
    setError(null);
    try {
      const result = await api.reflect(yaml, dataPath);
      if (result.success && result.yaml) {
        setYaml(result.yaml);
        setCertificate(result.certificate);
      } else {
        setError(
          `Reflection failed after ${result.attempts} attempt(s). Drafts: ${result.drafts.length}`
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reflection failed");
    } finally {
      setLoading(false);
      setAction("");
    }
  };

  const loadExample = (content: string) => {
    setYaml(content);
    setCertificate(null);
    setError(null);
  };

  const strategyName = certificate?.strategy_name || "my-strategy";
  const allPassed = certificate
    ? certificate.risk_constraints.every((c) => c.passed)
    : false;

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      {/* SideNavBar */}
      <nav className="fixed left-0 top-0 h-full z-50 bg-surface-container-low w-20 flex flex-col items-center py-md border-r border-outline-variant">
        <Link to="/" className="mt-2 mb-8">
          <div className="w-10 h-10 rounded border border-aureum-gold flex items-center justify-center bg-ink">
            <span className="font-display text-lg font-bold text-aureum-gold">A</span>
          </div>
        </Link>
        <div className="flex flex-col gap-xl font-mono-label text-mono-label w-full">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                disabled={!item.active}
                className={`flex flex-col items-center gap-xs py-sm scale-95 duration-200 transition-colors ${
                  item.active
                    ? "text-aureum-gold border-r-2 border-aureum-gold"
                    : "text-on-surface-variant hover:text-aureum-gold"
                }`}
              >
                <Icon className="w-5 h-5" strokeWidth={item.active ? 2 : 1.5} />
                <span style={{ fontSize: "10px" }}>{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* TopAppBar */}
      <nav className="fixed top-0 right-0 left-20 z-40 flex justify-between items-center bg-surface w-full h-16 px-margin-desktop border-b border-outline-variant">
        <div className="flex items-center gap-xl">
          <span className="font-display text-h2 font-medium text-aureum-gold">
            Aureum Studio
          </span>
          <div className="hidden md:flex gap-lg font-mono-label text-mono-label">
            {(["Mainnet", "Staging"] as const).map((env) => (
              <button
                key={env}
                onClick={() => setActiveEnv(env)}
                className={`transition-opacity ${
                  activeEnv === env
                    ? "text-aureum-gold font-bold opacity-100"
                    : "text-on-surface-variant opacity-80 hover:opacity-100"
                }`}
              >
                {env}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-md mr-20 text-slate">
          <button className="hover:text-aureum-gold transition-colors">
            <Activity className="w-5 h-5" strokeWidth={1.5} />
          </button>
          <button className="hover:text-aureum-gold transition-colors">
            <Bell className="w-5 h-5" strokeWidth={1.5} />
          </button>
          <div className="w-8 h-8 rounded-full bg-card border border-panel flex items-center justify-center ml-sm overflow-hidden">
            <span className="font-mono-label text-[10px] text-aureum-gold">SD</span>
          </div>
        </div>
      </nav>

      {/* Main Content Canvas */}
      <main className="ml-20 mt-16 p-lg h-[calc(100vh-64px)] grid grid-cols-12 gap-lg overflow-hidden">
        {/* Column 1: Author/Strategy Panel (3 cols) */}
        <aside className="col-span-3 flex flex-col gap-md border border-card bg-panel p-md stagger-1 h-full overflow-y-auto">
          <div className="border-b border-card pb-sm mb-sm">
            <span className="font-mono-label text-mono-label text-slate uppercase tracking-wider text-[10px]">
              Core Logic
            </span>
            <h1 className="text-2xl mt-unit text-cream font-display">Strategy Definition</h1>
          </div>

          {/* Strategy files list */}
          <div className="flex flex-col gap-sm mt-sm">
            {certificate && (
              <div className="p-sm border border-aureum-gold bg-card flex flex-col gap-xs cursor-pointer hover:bg-[#232f46] transition-colors relative">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-aureum-gold" />
                <div className="flex justify-between items-center pl-unit">
                  <span className="font-mono-data text-mono-data text-cream">{strategyName}.yaml</span>
                  <span className="font-mono-label text-[10px] text-deep-navy bg-aureum-gold px-1 rounded-sm">
                    Verified
                  </span>
                </div>
                <span className="font-body-md text-[12px] text-slate pl-unit">
                  Last run: just now
                </span>
              </div>
            )}
            {examples.map((ex) => (
              <div
                key={ex.name}
                onClick={() => loadExample(ex.content)}
                className="p-sm border border-card bg-ink flex flex-col gap-xs cursor-pointer hover:border-outline-variant transition-colors"
              >
                <div className="flex justify-between items-center">
                  <span className="font-mono-data text-mono-data text-slate">{ex.name}</span>
                  <span className="font-mono-label text-[10px] text-slate border border-card px-1 rounded-sm">
                    Example
                  </span>
                </div>
                <span className="font-body-md text-[12px] text-outline-variant">
                  Click to load
                </span>
              </div>
            ))}
          </div>

          {/* Author with Claude */}
          <div className="mt-4 border-t border-card pt-md">
            <div className="flex items-center gap-2 text-cream font-semibold text-sm mb-3">
              <Sparkles className="w-4 h-4 text-aureum-gold" />
              Author with Claude
            </div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe a strategy, e.g. 'Low volatility tech stocks, top 20%, equal weights, max drawdown 25%'"
              className="w-full h-20 bg-ink border border-card rounded p-3 text-sm text-cream placeholder:text-outline-variant resize-none focus:outline-none focus:border-aureum-gold"
            />
            <button
              onClick={handleAuthor}
              disabled={loading || !prompt.trim()}
              className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-deep-navy bg-aureum-gold hover:bg-primary transition-colors rounded disabled:opacity-50"
            >
              {action === "author" ? (
                <span className="w-3 h-3 border-2 border-deep-navy/30 border-t-deep-navy rounded-full animate-spin" />
              ) : (
                <Sparkles className="w-3 h-3" />
              )}
              Generate YAML
            </button>
          </div>

          {/* Data selector */}
          <div className="mt-2">
            <div className="flex items-center gap-2 text-cream font-semibold text-sm mb-3">
              <BarChart className="w-4 h-4 text-aureum-gold" />
              Data Source
            </div>
            <select
              value={dataPath}
              onChange={(e) => setDataPath(e.target.value)}
              className="w-full bg-ink border border-card text-cream text-xs rounded px-2 py-1.5 focus:outline-none focus:border-aureum-gold"
            >
              {dataFiles.map((df) => (
                <option key={df.path} value={df.path}>
                  {df.name}
                </option>
              ))}
            </select>
          </div>

          {/* Signals */}
          <div>
            <div className="flex items-center gap-2 text-cream font-semibold text-sm mb-3">
              <ShieldCheck className="w-4 h-4 text-aureum-gold" />
              Signals
            </div>
            <div className="flex flex-wrap gap-1">
              {signals.map((s) => (
                <span
                  key={s}
                  className="px-2 py-1 text-[10px] font-mono bg-ink border border-card text-slate rounded"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>

          <button className="mt-auto border border-card text-cream bg-transparent py-sm font-mono-label text-mono-label hover:border-aureum-gold transition-colors flex items-center justify-center gap-sm">
            <Plus className="w-4 h-4" />
            New Strategy File
          </button>
        </aside>

        {/* Column 2: YAML Editor (6 cols) */}
        <section className="col-span-6 border border-card bg-ink flex flex-col stagger-2 h-full relative">
          <div className="flex justify-between items-center border-b border-card p-sm bg-panel">
            <div className="flex items-center gap-sm">
              <Code className="w-4 h-4 text-slate" />
              <span className="font-mono-data text-mono-data text-cream">{strategyName}.yaml</span>
            </div>
            <div className="flex items-center gap-md">
              <span className="font-mono-data text-[10px] text-slate">Ln 42, Col 18</span>
              <button className="text-slate hover:text-aureum-gold transition-colors">
                <Save className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <StrategyEditor value={yaml} onChange={setYaml} />
          </div>
          {/* Floating action bar inside editor */}
          <div className="absolute bottom-4 right-4 bg-panel border border-card p-1 flex gap-1 shadow-lg">
            <button
              className="p-1 text-slate hover:text-cream hover:bg-card transition-colors"
              title="Format Code"
            >
              <AlignLeft className="w-4 h-4" />
            </button>
            <button
              className="p-1 text-slate hover:text-cream hover:bg-card transition-colors"
              title="Validate Logic"
            >
              <ShieldCheck className="w-4 h-4" />
            </button>
          </div>
        </section>

        {/* Column 3: Results & Certificate (3 cols) */}
        <aside className="col-span-3 flex flex-col gap-md stagger-3 h-full overflow-y-auto">
          {/* High-level metrics */}
          <div className="grid grid-cols-2 gap-sm">
            <div className="bg-card border border-panel p-sm relative pt-6">
              <div className="absolute top-0 left-0 w-full h-[2px] bg-aureum-gold" />
              <span className="font-mono-label text-[10px] text-slate uppercase">Sharpe</span>
              <div className="font-mono-data text-lg text-cream mt-1">
                {certificate?.results.sharpe_ratio?.toFixed(2) ?? "—"}
              </div>
            </div>
            <div className="bg-card border border-panel p-sm relative pt-6">
              <span className="font-mono-label text-[10px] text-slate uppercase">Max DD</span>
              <div className="font-mono-data text-lg text-error mt-1">
                {formatPct(certificate?.results.max_drawdown)}
              </div>
            </div>
            <div className="bg-card border border-panel p-sm col-span-2 relative pt-6">
              <span className="font-mono-label text-[10px] text-slate uppercase">Volatility (Ann.)</span>
              <div className="font-mono-data text-lg text-cream mt-1">
                {formatPct(certificate?.results.volatility_annual)}
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-card border border-panel p-sm">
            <div className="font-mono-label text-[10px] text-slate uppercase mb-2">NAV Curve</div>
            <BacktestChart certificate={certificate} />
          </div>

          {/* The Aureum Certificate */}
          <CertificateSeal
            compact
            strategyName={strategyName}
            strategyHash={certificate?.inputs.strategy.sha256}
            generatedAt={certificate?.generated_at}
            passed={allPassed}
            className="aspect-square mt-md stagger-4"
          />

          {/* Risk constraint summary */}
          {certificate && (
            <div className="bg-card border border-panel p-sm">
              <div className="font-mono-label text-[10px] text-slate uppercase mb-2">
                Risk Constraints
              </div>
              <div className="space-y-1">
                {certificate.risk_constraints.map((c) => (
                  <div
                    key={c.name}
                    className={`flex items-center justify-between text-[11px] font-mono-data px-2 py-1 rounded ${
                      c.passed
                        ? "bg-surface-container-high text-on-surface"
                        : c.hard
                        ? "bg-error-container/20 text-error"
                        : "bg-surface-container-high text-warning"
                    }`}
                  >
                    <span>{c.name.replace(/_/g, " ")}</span>
                    <span>{c.passed ? "PASS" : c.hard ? "HARD FAIL" : "SOFT"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Phase 4 lineage */}
          {certificate && <Phase4Lineage certificate={certificate} />}

          {/* Live trading */}
          <LiveTradingPanel
            strategyYaml={yaml}
            dataPath={dataPath}
            disabled={loading}
          />

          {/* Error */}
          {error && (
            <div className="p-3 rounded bg-error-container/10 border border-error/30 text-error text-sm font-body-md">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="mt-auto flex flex-col gap-sm">
            <button
              onClick={handleReflect}
              disabled={loading}
              className="border border-card text-cream bg-transparent py-sm font-mono-label text-mono-label hover:border-aureum-gold transition-colors flex items-center justify-center gap-sm disabled:opacity-50"
            >
              {action === "reflect" ? (
                <span className="w-4 h-4 border-2 border-on-surface-variant/30 border-t-aureum-gold rounded-full animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Reflect
            </button>
            <button
              onClick={handleBacktest}
              disabled={loading}
              className="bg-primary-container text-deep-navy font-mono-label text-mono-label font-bold py-md px-lg w-full flex items-center justify-center gap-sm hover:bg-primary transition-colors disabled:opacity-50"
            >
              {action === "backtest" ? (
                <span className="w-4 h-4 border-2 border-deep-navy/30 border-t-deep-navy rounded-full animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Run Backtest
            </button>
          </div>
        </aside>
      </main>
    </div>
  );
}
