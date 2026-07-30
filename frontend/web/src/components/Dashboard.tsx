import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Sparkles,
  RotateCcw,
  FileCode,
  Database,
  Activity,
  Loader2,
} from "lucide-react";
import { api } from "../api";
import type { Certificate, DataFile, Example } from "../types";
import StrategyEditor from "./StrategyEditor";
import CertificateViewer from "./CertificateViewer";
import BacktestChart from "./BacktestChart";

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

export default function Dashboard() {
  const [yaml, setYaml] = useState(DEFAULT_STRATEGY);
  const [prompt, setPrompt] = useState("");
  const [dataPath, setDataPath] = useState("examples/data/synthetic_prices.csv");
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [signals, setSignals] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<"" | "author" | "backtest" | "reflect">(
    ""
  );
  const [error, setError] = useState<string | null>(null);

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
          `Reflection failed after ${result.attempts} attempt(s). Drafts: ${
            result.drafts.length
          }`
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

  return (
    <div className="min-h-screen bg-aureum-ink flex flex-col">
      {/* Header */}
      <header className="border-b border-aureum-panel bg-aureum-panel/50">
        <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="flex items-center gap-2 text-aureum-muted hover:text-aureum-cream transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="text-sm">Back</span>
            </Link>
            <div className="h-5 w-px bg-aureum-panel" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded bg-aureum-gold flex items-center justify-center">
                <span className="font-display font-bold text-aureum-ink">A</span>
              </div>
              <span className="font-display text-lg font-semibold text-aureum-cream">
                Aureum Studio
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleReflect}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-aureum-cream border border-aureum-muted hover:border-aureum-gold rounded disabled:opacity-50"
            >
              {action === "reflect" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Reflect
            </button>
            <button
              onClick={handleBacktest}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-aureum-ink bg-aureum-gold hover:bg-aureum-gold-soft rounded disabled:opacity-50"
            >
              {action === "backtest" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Run Backtest
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-12 overflow-hidden">
        {/* Sidebar */}
        <aside className="col-span-2 border-r border-aureum-panel bg-aureum-panel/30 overflow-auto">
          <div className="p-4 space-y-6">
            <div>
              <div className="flex items-center gap-2 text-aureum-cream text-sm font-semibold mb-3">
                <FileCode className="w-4 h-4 text-aureum-gold" />
                Examples
              </div>
              <div className="space-y-1">
                {examples.map((ex) => (
                  <button
                    key={ex.name}
                    onClick={() => loadExample(ex.content)}
                    className="w-full text-left px-2 py-1.5 text-xs text-aureum-slate hover:text-aureum-cream hover:bg-aureum-panel rounded truncate"
                  >
                    {ex.name}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 text-aureum-cream text-sm font-semibold mb-3">
                <Database className="w-4 h-4 text-aureum-gold" />
                Data
              </div>
              <select
                value={dataPath}
                onChange={(e) => setDataPath(e.target.value)}
                className="w-full bg-aureum-card border border-aureum-panel text-aureum-cream text-xs rounded px-2 py-1.5"
              >
                {dataFiles.map((df) => (
                  <option key={df.path} value={df.path}>
                    {df.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="flex items-center gap-2 text-aureum-cream text-sm font-semibold mb-3">
                <Activity className="w-4 h-4 text-aureum-gold" />
                Signals
              </div>
              <div className="flex flex-wrap gap-1">
                {signals.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-1 text-[10px] font-mono bg-aureum-card border border-aureum-panel text-aureum-slate rounded"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* Main editor area */}
        <main className="col-span-5 flex flex-col border-r border-aureum-panel min-h-0">
          <div className="p-4 border-b border-aureum-panel">
            <div className="flex items-center gap-2 text-aureum-cream font-semibold text-sm mb-3">
              <Sparkles className="w-4 h-4 text-aureum-gold" />
              Author a strategy
            </div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe a strategy, e.g. 'Low volatility tech stocks, top 20%, equal weights, max drawdown 25%'"
              className="w-full h-20 bg-aureum-card border border-aureum-panel rounded p-3 text-sm text-aureum-cream placeholder:text-aureum-muted resize-none focus:outline-none focus:border-aureum-gold"
            />
            <button
              onClick={handleAuthor}
              disabled={loading || !prompt.trim()}
              className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-aureum-ink bg-aureum-gold hover:bg-aureum-gold-soft rounded disabled:opacity-50"
            >
              {action === "author" ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Sparkles className="w-3 h-3" />
              )}
              Generate with Claude
            </button>
          </div>

          <div className="flex-1 min-h-0 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-aureum-cream uppercase tracking-wider">
                Strategy YAML
              </span>
            </div>
            <StrategyEditor value={yaml} onChange={setYaml} />
          </div>
        </main>

        {/* Results panel */}
        <section className="col-span-5 flex flex-col min-h-0 overflow-auto">
          {error && (
            <div className="m-4 p-3 rounded bg-aureum-danger/10 border border-aureum-danger/30 text-aureum-danger text-sm">
              {error}
            </div>
          )}

          <div className="p-4 border-b border-aureum-panel">
            <div className="text-xs font-semibold text-aureum-cream uppercase tracking-wider mb-3">
              NAV Curve
            </div>
            <BacktestChart certificate={certificate} />
          </div>

          <div className="flex-1 min-h-0">
            <CertificateViewer certificate={certificate} />
          </div>
        </section>
      </div>
    </div>
  );
}
