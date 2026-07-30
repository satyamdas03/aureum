"""AI-driven reflection loop that fixes failing Aureum strategies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ai import (
    AnthropicClient,
    DEFAULT_MODEL,
    _extract_yaml,
    build_reflector_prompt,
)
from .backtest import BacktestRunner, MarketData
from .certificate import BacktestCertificate, get_environment
from .strategy import Strategy


@dataclass
class ReflectionResult:
    """Result of a reflection run."""

    success: bool
    attempts: int
    drafts: list[Path]
    accepted_draft: Path | None
    final_certificate: BacktestCertificate | None


class StrategyReflector:
    """Diagnose a failing strategy from a certificate and propose YAML fixes."""

    def __init__(
        self,
        client: AnthropicClient | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.client = client or AnthropicClient(model=model)

    def _load_or_build_certificate(
        self,
        strategy: Strategy,
        strategy_path: Path,
        data_path: Path,
        certificate_path: Path | None,
    ) -> BacktestCertificate:
        if certificate_path is not None:
            raw = Path(certificate_path).read_text(encoding="utf-8")
            data = json.loads(raw)
            return BacktestCertificate(**data)

        data_obj = MarketData.from_csv(data_path)
        runner = BacktestRunner(
            strategy, data_obj, data_source=str(data_path)
        )
        env = get_environment(aureum_version="0.2.0", cwd=data_path.parent)
        return runner.build_certificate(
            strategy_path=strategy_path,
            data_path=data_path,
            environment=env,
        )

    @staticmethod
    def _has_hard_failures(certificate: BacktestCertificate) -> bool:
        for item in certificate.risk_constraints:
            if not item.get("passed", True) and item.get("hard", False):
                return True
        return False

    @staticmethod
    def _next_draft_path(output_path: Path, attempt: int) -> Path:
        return output_path.with_suffix(f".{attempt:03d}{output_path.suffix}")

    def reflect(
        self,
        strategy_path: str | Path,
        data_path: str | Path,
        *,
        certificate_path: str | Path | None = None,
        max_attempts: int = 3,
        output_path: str | Path | None = None,
    ) -> ReflectionResult:
        """Run the reflection loop.

        Saves numbered drafts for every failed attempt. Overwrites the output
        file only when all hard constraints pass.
        """
        strategy_path = Path(strategy_path)
        data_path = Path(data_path)
        output_path = Path(output_path) if output_path else strategy_path

        strategy = Strategy.from_file(strategy_path)
        certificate = self._load_or_build_certificate(
            strategy,
            strategy_path,
            data_path,
            Path(certificate_path) if certificate_path else None,
        )

        drafts: list[Path] = []
        current_yaml = strategy_path.read_text(encoding="utf-8")

        for attempt in range(1, max_attempts + 1):
            if not self._has_hard_failures(certificate):
                # Already passes; nothing to fix.
                return ReflectionResult(
                    success=True,
                    attempts=0,
                    drafts=[],
                    accepted_draft=None,
                    final_certificate=certificate,
                )

            prompt = build_reflector_prompt(current_yaml, certificate.to_dict())
            response = self.client.complete(prompt)
            new_yaml = _extract_yaml(response)
            new_strategy = Strategy.from_yaml(new_yaml)
            validation_errors = new_strategy.validate()

            if validation_errors:
                # Invalid YAML: save as a draft anyway for forensics, but do not run.
                draft_path = self._next_draft_path(output_path, attempt)
                draft_path.write_text(new_yaml, encoding="utf-8")
                drafts.append(draft_path)
                current_yaml = new_yaml
                continue

            # Run backtest on the candidate.
            data_obj = MarketData.from_csv(data_path)
            runner = BacktestRunner(
                new_strategy, data_obj, data_source=str(data_path)
            )
            env = get_environment(aureum_version="0.2.0", cwd=data_path.parent)
            certificate = runner.build_certificate(
                strategy_path=strategy_path,
                data_path=data_path,
                environment=env,
            )

            if not self._has_hard_failures(certificate):
                output_path.write_text(new_yaml, encoding="utf-8")
                certificate = certificate.with_draft_lineage(
                    {
                        "attempts": attempt,
                        "drafts": [str(d) for d in drafts],
                        "accepted": str(output_path),
                    }
                )
                return ReflectionResult(
                    success=True,
                    attempts=attempt,
                    drafts=drafts,
                    accepted_draft=output_path,
                    final_certificate=certificate,
                )

            draft_path = self._next_draft_path(output_path, attempt)
            draft_path.write_text(new_yaml, encoding="utf-8")
            drafts.append(draft_path)
            current_yaml = new_yaml

        return ReflectionResult(
            success=False,
            attempts=max_attempts,
            drafts=drafts,
            accepted_draft=None,
            final_certificate=certificate,
        )
