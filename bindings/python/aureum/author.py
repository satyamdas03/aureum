"""AI-assisted Aureum strategy authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from aureum import __version__

from .ai import (
    DEFAULT_MODEL,
    AnthropicClient,
    StrategyAIError,
    _extract_yaml,
    build_author_prompt,
    build_refinement_prompt,
)
from .backtest import BacktestRunner, MarketData
from .certificate import get_environment
from .strategy import Strategy


@dataclass
class AuthorResult:
    """Result of an authoring run."""

    yaml_text: str
    rationale: str
    certificate_path: Path | None = None


class StrategyAuthor:
    """Turn a natural-language prompt into a validated Aureum strategy YAML."""

    def __init__(
        self,
        client: AnthropicClient | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.client = client or AnthropicClient(model=model)

    def from_prompt(
        self,
        prompt: str,
        *,
        example_strategy: str | None = None,
        max_correction_attempts: int = 2,
    ) -> tuple[str, str]:
        """Generate validated YAML from a user prompt.

        Returns `(yaml_text, rationale)`.
        """
        current_prompt = build_author_prompt(prompt, example_strategy=example_strategy)
        last_yaml = ""

        for attempt in range(1 + max_correction_attempts):
            response = self.client.complete(current_prompt)
            try:
                last_yaml = _extract_yaml(response)
            except StrategyAIError as exc:
                if attempt == max_correction_attempts:
                    raise StrategyAIError(
                        f"LLM never returned a YAML block. Last response:\n{response}"
                    ) from exc
                current_prompt += (
                    "\n\nYour previous response did not contain a valid YAML block. "
                    "Return ONLY a fenced YAML block using ```yaml."
                )
                continue

            try:
                strategy = Strategy.from_yaml(last_yaml)
                errors = strategy.validate()
            except (yaml.YAMLError, ValueError) as exc:
                errors = [str(exc)]

            if not errors:
                rationale = self._extract_rationale(response)
                return last_yaml, rationale

            if attempt == max_correction_attempts:
                raise StrategyAIError(
                    f"Could not produce valid YAML after {attempt} correction attempts. "
                    f"Last validation errors: {errors}"
                )

            current_prompt = build_refinement_prompt(prompt, last_yaml, errors)

        # Unreachable, but keeps mypy happy.
        return last_yaml, ""

    @staticmethod
    def _extract_rationale(response: str) -> str:
        for line in response.splitlines():
            if line.strip().lower().startswith("rationale:"):
                return line.split(":", 1)[1].strip()
        return ""

    def write_strategy(
        self,
        prompt: str,
        output_path: Path,
        *,
        example_strategy: str | None = None,
        dry_run_data: Path | None = None,
        max_correction_attempts: int = 2,
    ) -> AuthorResult:
        """Generate YAML, optionally dry-run it, and write it to disk."""
        yaml_text, rationale = self.from_prompt(
            prompt,
            example_strategy=example_strategy,
            max_correction_attempts=max_correction_attempts,
        )

        output_path = Path(output_path)
        output_path.write_text(yaml_text, encoding="utf-8")

        cert_path: Path | None = None
        if dry_run_data is not None:
            strategy = Strategy.from_yaml(yaml_text)
            data = MarketData.from_csv(dry_run_data)
            runner = BacktestRunner(
                strategy, data, data_source=str(dry_run_data)
            )
            env = get_environment(aureum_version=__version__, cwd=output_path.parent)
            cert = runner.build_certificate(
                strategy_path=output_path,
                data_path=dry_run_data,
                environment=env,
            )
            cert_path = output_path.with_suffix(".certificate.json")
            cert_path.write_text(cert.to_json(indent=2), encoding="utf-8")

        return AuthorResult(
            yaml_text=yaml_text,
            rationale=rationale,
            certificate_path=cert_path,
        )
