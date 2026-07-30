export interface Example {
  name: string;
  path: string;
  content: string;
}

export interface DataFile {
  name: string;
  path: string;
}

export interface RiskConstraint {
  name: string;
  limit: number;
  actual: number;
  operator: string;
  passed: boolean;
  hard: boolean;
}

export interface BacktestResults {
  final_nav: number;
  total_return: number;
  cagr: number;
  volatility_annual: number;
  sharpe_ratio: number | null;
  max_drawdown: number;
  turnover_annual: number;
}

export interface Certificate {
  aureum_version: string;
  generated_at: string;
  strategy_name: string;
  inputs: {
    strategy: { path: string; sha256: string; metadata: Record<string, unknown> };
    data: { path: string; sha256: string; metadata: Record<string, unknown> };
  };
  results: BacktestResults;
  risk_constraints: RiskConstraint[];
  execution_trace?: {
    daily_nav: Array<{ date: string; nav: number }>;
    rebalance_log: Array<Record<string, unknown>>;
  };
}
