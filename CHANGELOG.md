# Changelog

All notable changes to the Aureum project are documented in this file.

## 0.4.0 — Provable Portfolio Construction + Seven Revolutionary Edges

### Added
- **Edge 1 — Classical MPT**: mean-variance, GMVP, max-Sharpe, risk-parity, and min-CVaR optimizers in `aureum.mpt` with lineage recorded in the backtest certificate.
- **Edge 2 — Causal MPT**: condition covariance on declared latent drivers via `aureum.causal`; certificate records `causal_graph_hash`, `conditional_covariance_hash`, and per-rebalance driver betas/R².
- **Edge 3 — Conformal portfolios**: replace point forecasts with conservative split-conformal prediction sets in `aureum.conformal`; certificate records `calibration_set_hash`, `coverage_level`, and `prediction_set_width`.
- **Edge 4 — Neuro-symbolic alpha**: deterministic, auditable formulas generated from a whitelist grammar in `aureum.alpha`; certificate records `alpha_lineage`, formula, safety verdict, and generation provenance.
- **Edge 5 — Semantic knowledge graph**: content-addressed entities and typed relations across the investment process in `aureum.graph`; certificate records `graph_node_id`, `linked_entity_hashes`, and the full `knowledge_graph`.
- **Edge 6 — Differentiable certifiable execution**: JAX/Optax learned Sharpe policy in `aureum.diffopt`; certificate records `model_architecture_hash`, `weights_hash`, and train/val/test split hashes.
- **Edge 7 — Economic-security audit**: adversarial extractable-value analysis against front-running and liquidity squeezes in `aureum.econsec`; certificate records an `economic_security` block plus `economic_security_hash` in determinism.
- New CLI commands: `aureum frontier`, `aureum alpha`, and extended `aureum backtest --graph` / `--economic-security` flags.

### Changed
- README refreshed for v0.4.0: added the seven-edge table, new CLI examples, and roadmap status marking Phase 4 complete.

### Fixed
- Version references in README and `bindings/python/pyproject.toml` aligned to 0.4.0.

## 0.3.0 — Self-Proving Backtest Certificate

- Initial public alpha with deterministic strategy DSL, backtest runner, and the first Aureum Backtest Certificate (ABC).
- CLI commands: `aureum backtest`, `aureum snapshot`, `aureum author`, `aureum reflect`.
- Dimensional-type groundwork, real data adapters, and the AI authoring + reflection loop.
