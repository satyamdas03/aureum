# Aureum v0.4.2 — Live Alpaca Paper Trading Design

Date: 2026-08-02  
Status: Approved → Implementation in progress  
Owner: Bull / Aureum agent  

## 1. Goal

Build a production-grade **Alpaca paper-trading bridge** so Aureum strategies can execute real orders against real market data while remaining sandboxed to Alpaca paper accounts. The first validated strategy will be the Phase 4 hero strategy (`examples/strategies/hero_phase4_live.yaml`).

## 2. Scope for v0.4.2

- New module: `aureum.trading` — Alpaca trading API adapter (no new deps, stdlib `urllib`)
- New module: `aureum.execution` — `ExecutionBackend` protocol + simulated + paper backends
- Refactor: `aureum.backtest.BacktestRunner` — extract rebalance into backend-agnostic phases
- Extend: `aureum.certificate` — live account/order/fill lineage
- New CLI: `aureum live` and `aureum account`
- Scripts: PowerShell daily task wrapper + Windows Task Scheduler registration helper
- Tests: mocked Alpaca trading API, backend unit tests, live CLI tests
- Docs/memory update after validation

Out of scope: real-money execution, options/futures, long-running daemon, cloud scheduling.

## 3. Execution Model: B — Local Scheduler (Windows Task Scheduler)

No persistent process. A Windows scheduled task invokes a PowerShell wrapper once per market day at 09:30 local, optionally again at 12:30, with an end-of-day summary at 16:05. The wrapper:

1. Loads `.env` from the repo root
2. Runs `aureum live --paper --config ... --certificate logs/live-{date}.json`
3. Redirects stdout/stderr to `logs/aureum-live-{date}.log`
4. Exits with the same code; Task Scheduler records success/failure

Later, the same CLI can be triggered by cron/systemd/Lambda without changing core code.

## 4. Components

### 4.1 `aureum.trading.AlpacaTradingAdapter`

Direct `urllib` calls to `https://paper-api.alpaca.markets/v2`.

Methods:

```python
get_clock() -> dict
get_account() -> AccountSnapshot
get_positions() -> list[PositionRecord]
get_orders(status="open") -> list[OrderRecord]
submit_market_order(symbol, qty, side, client_order_id, time_in_force="day") -> dict
submit_notional_order(symbol, notional, side, client_order_id, time_in_force="day") -> dict
cancel_order(order_id: str) -> dict
cancel_all_orders() -> dict
```

Safety guards in `submit_*`:
- `paper_only` flag (default `True`) checks endpoint + env `AUREUM_FORCE_LIVE`
- `market_open_required` checks `get_clock()` unless `--ignore-market-hours`
- Maximum order value guard
- Deterministic `client_order_id = f"aureum-{run_id}-{symbol}-{side}"` for idempotency

Errors raise typed exceptions: `MarketClosedError`, `BuyingPowerError`, `OrderSubmissionError`, `RiskViolationError`, `KillSwitchActive`.

### 4.2 `aureum.execution`

```python
@dataclass
class AccountSnapshot: ...

@dataclass
class PositionRecord: ...

@dataclass
class TargetOrder: symbol: str; target_notional: float; side: str; current_qty: float

@dataclass
class SubmittedOrder: ...

class ExecutionBackend(Protocol):
    async def load_account(self) -> AccountSnapshot: ...
    async def load_positions(self) -> dict[str, PositionRecord]: ...
    async def submit_orders(self, orders: list[TargetOrder]) -> list[SubmittedOrder]: ...
    async def finalize(self) -> dict: ...

class SimulatedExecutionBackend: ...
class AlpacaPaperExecutionBackend: ...
```

`SimulatedExecutionBackend` preserves existing backtest behavior exactly.

### 4.3 `AlpacaPaperExecutionBackend` rebalance algorithm

1. Load account snapshot and current positions
2. Compute target notional per symbol from strategy weights × portfolio equity
3. Compute target qty per symbol using latest prices (from data adapter snapshot)
4. For each symbol: `delta = target_qty - current_qty`
5. Drop deltas below `min_order_notional` or below minimum share qty
6. Submit diff orders (market or notional depending on config)
7. Poll fills for up to `fill_timeout_seconds`
8. Return `LiveExecutionResult` with order records, fill prices, post-trade account snapshot

### 4.4 Certificate extension

`aureum.certificate` adds:

```python
@dataclass
class AccountSnapshot: ...

@dataclass
class OrderRecord: ...

@dataclass
class LiveTradingCertificate:
    timestamp: str
    run_id: str
    config_path: str
    git_commit: str | None
    pre_trade_account: AccountSnapshot
    post_trade_account: AccountSnapshot
    target_weights: dict[str, float]
    target_quantities: dict[str, float]
    current_positions: list[PositionRecord]
    orders: list[OrderRecord]
    risk_checks: list[dict]
    errors: list[str]
    metadata: dict
```

`BacktestCertificate` is left unchanged; `LiveTradingCertificate` is a sibling.

### 4.5 CLI commands

```
aureum live --config PATH --certificate PATH [--paper | --live]
              [--check-only] [--dry-run] [--ignore-market-hours]
              [--kill-switch PATH]

aureum account [--paper | --live]
```

`--check-only`: load config, compute target portfolio, print diagnostics, do not submit orders.  
`--dry-run`: print intended orders, do not submit.  
`--paper`: default; uses paper-api endpoint.  
`--live`: requires `AUREUM_FORCE_LIVE=true` and uses `https://api.alpaca.markets/v2`.

### 4.6 Safety guardrails

| Guardrail | Default | Override |
|---|---|---|
| Paper-only mode | required | `AUREUM_FORCE_LIVE=true` + `--live` |
| Market open check | required | `--ignore-market-hours` |
| Max single position | 25% equity | config `max_single_position_pct` |
| Max total invested | 95% equity | config `max_total_invested_pct` |
| Max positions | 20 | config `max_positions` |
| Min order notional | $1.00 | config `min_order_notional` |
| Kill switch file | none | `AUREUM_KILL_SWITCH` env path |
| Idempotency | deterministic `client_order_id` | per-run UUID suffix |

### 4.7 Error codes

- `0` — success or kill switch active
- `1` — unexpected error
- `2` — market closed (`MarketClosedError`)
- `3` — insufficient buying power (`BuyingPowerError`)
- `4` — order submission failed (`OrderSubmissionError`)
- `5` — risk guardrail violated (`RiskViolationError`)

## 5. Data Flow for One Run

```
Windows Task Scheduler 09:30
  → scripts/aureum-daily-task.ps1
    → load .env
    → aureum live --paper --config examples/strategies/hero_phase4_live.yaml \
                  --certificate logs/live-2026-08-02.json
      1. Check kill switch
      2. Check market hours
      3. Load strategy config + Alpaca data adapter
      4. Strategy computes target weights
      5. AlpacaPaperExecutionBackend reconciles and submits diff orders
      6. Poll fills, capture post-trade account snapshot
      7. Write LiveTradingCertificate JSON
      8. Print summary
    → capture exit code + log
```

## 6. Testing

- `test_trading.py`: mock Alpaca trading endpoints for clock, account, positions, orders, submit/cancel
- `test_execution_backend.py`: test `SimulatedExecutionBackend` parity with old backtest and `AlpacaPaperExecutionBackend` diff logic
- `test_live_cli.py`: click runner for `aureum live --check-only` and `aureum account`
- Add mocked trading responses to existing `test_adapter.py` if it already covers data endpoints

## 7. File Plan

```
aureum/
  trading.py                  # AlpacaTradingAdapter + exceptions
  execution.py                # ExecutionBackend protocol + backends
  backtest.py                 # refactored rebalance loop
  cli.py                      # aureum live + aureum account
  certificate.py              # LiveTradingCertificate dataclasses
scripts/
  aureum-daily-task.ps1
  register-scheduled-task.ps1
  .env.example
docs/superpowers/specs/2026-08-02-aureum-live-trading-design.md  # this file
tests/
  test_trading.py
  test_execution_backend.py
  test_live_cli.py
```

## 8. Dependencies

No new runtime dependencies. Tests may use `responses` or `unittest.mock` + `urllib` monkeypatch. Ruff/mypy must remain clean.

## 9. Acceptance Criteria

- [ ] `aureum account --paper` prints account and positions using live Alpaca paper keys
- [ ] `aureum live --paper --check-only --config hero_phase4_live.yaml` computes targets without orders
- [ ] `aureum live --paper --dry-run ...` prints intended orders and stops
- [ ] A real paper run submits fractional/whole-share orders and writes a `LiveTradingCertificate`
- [ ] All existing tests still pass (`pytest` in `bindings/python`)
- [ ] New trading/backend/CLI tests pass
- [ ] ruff + mypy clean
- [ ] Windows scheduled task registered and one manual run succeeds
- [ ] Memory dossiers updated

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Accidental live-money order | Paper endpoint default; `--live` requires explicit env and CLI flag; endpoint constant guarded in code |
| Duplicate orders on rerun | Deterministic `client_order_id`; existing open orders checked before submission |
| Oversized position | Max single/total exposure guardrails; fail fast before submission |
| Market closed run | Exit code 2; scheduler should only fire M–F but the CLI also checks |
| Network/API failure | Each order recorded; partial-fill certificate written; errors captured |
| Windows sleep/hibernation | Task Scheduler wakes the machine if “wake to run” is enabled in registration script |

## 11. Next Steps After This Spec

1. Implement `aureum.trading`
2. Implement `aureum.execution`
3. Refactor `aureum.backtest`
4. Extend `aureum.certificate`
5. Add CLI commands
6. Add tests
7. Add PowerShell scripts
8. Manual paper-account validation
9. Memory update + v0.4.2 release notes
