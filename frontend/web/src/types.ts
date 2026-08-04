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

export interface PortfolioConstruction {
  objective: string;
  risk_measure: string;
  covariance_estimator: string;
  risk_free_rate: number;
  constraints: Record<string, unknown>;
  weights_history: Array<Record<string, unknown>>;
  frontier_hash?: string;
  optimization_inputs_hash?: string;
  calibration_set_hash?: string;
  coverage_level?: number;
  prediction_set_width?: number;
  causal_graph_hash?: string;
  conditional_covariance_hash?: string;
  model_architecture_hash?: string;
  weights_hash?: string;
  train_val_test_split_hashes?: Record<string, string>;
}

export interface AlphaSignal {
  name: string;
  formula: string;
  safety_checks_passed: boolean;
  llm_model?: string;
  prompt?: string;
}

export interface AlphaLineage {
  alpha_signals: AlphaSignal[];
}

export interface EconomicSecurity {
  enabled: boolean;
  replay_inputs_hash?: string;
  attack_vectors?: string[];
}

export interface KnowledgeGraph {
  entities: Array<Record<string, unknown>>;
  relations?: Array<Record<string, unknown>>;
}

export interface LiveOrder {
  symbol: string;
  side: string;
  delta_qty?: number;
  target_qty?: number;
  estimated_notional?: number;
  dry_run?: boolean;
  qty_filled?: number;
  filled_avg_price?: number;
  status?: string;
  [key: string]: unknown;
}

export interface LiveCertificate {
  aureum_version: string;
  certificate_spec_version: string;
  generated_at: string;
  run_id: string;
  live_mode: string;
  strategy_path: string;
  strategy_sha256: string;
  data_path: string | null;
  data_sha256: string | null;
  market_clock: Record<string, unknown>;
  pre_trade_account: Record<string, unknown>;
  post_trade_account: Record<string, unknown>;
  target_portfolio: Record<string, unknown>;
  current_positions: Array<Record<string, unknown>>;
  orders: LiveOrder[];
  risk_checks: Array<Record<string, unknown>>;
  errors: string[];
  metadata: Record<string, unknown>;
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
  portfolio_construction?: PortfolioConstruction;
  alpha_lineage?: AlphaLineage;
  knowledge_graph?: KnowledgeGraph;
  graph_node_id?: string;
  linked_entity_hashes?: string[];
  economic_security?: EconomicSecurity;
  determinism?: {
    input_hash: string;
    result_hash: string;
    tolerance: string;
    economic_security_hash?: string;
  };
}
