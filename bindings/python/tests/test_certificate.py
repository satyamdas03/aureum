"""Tests for the Aureum Backtest Certificate builder and schema."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aureum import __version__
from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import (
    BacktestCertificate,
    Environment,
    get_environment,
    hash_file,
)
from aureum.cli import cli
from aureum.strategy import Strategy

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_hash_file_is_stable():
    h1 = hash_file(EXAMPLE_DATA)
    h2 = hash_file(EXAMPLE_DATA)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_certificate_from_run_has_required_claims():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))

    env = Environment(
        aureum_version=__version__,
        git_commit="abc1234",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=env
    )

    assert isinstance(cert, BacktestCertificate)
    assert cert.certificate_spec_version == "1.0"
    assert cert.environment.git_commit == "abc1234"
    assert cert.inputs.strategy.sha256 == hash_file(EXAMPLE_STRATEGY)
    assert cert.inputs.data.sha256 == hash_file(EXAMPLE_DATA)
    assert cert.execution.trades > 0
    assert cert.execution.rebalance_count > 0
    assert 0.0 <= cert.results.max_drawdown <= 1.0
    assert cert.determinism.input_hash
    assert cert.determinism.result_hash

    names = {c["name"] for c in cert.risk_constraints}
    assert "max_drawdown" in names
    assert "max_leverage" in names


def test_certificate_to_dict_serializes():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = get_environment(aureum_version=__version__)
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=env
    )

    d = cert.to_dict()
    assert d["aureum_version"] == __version__
    assert d["certificate_spec_version"] == "1.0"
    assert "environment" in d
    assert "inputs" in d
    assert "execution" in d
    assert "results" in d
    assert "risk_constraints" in d
    assert "execution_trace" in d
    assert "determinism" in d


def test_certificate_is_deterministic():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = Environment(
        aureum_version=__version__,
        git_commit="abc1234",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )
    cert1 = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=env
    )
    cert2 = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=env
    )
    assert cert1.determinism.input_hash == cert2.determinism.input_hash
    assert cert1.determinism.result_hash == cert2.determinism.result_hash


def test_cli_writes_certificate(tmp_path: Path) -> None:
    cert_path = tmp_path / "certificate.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--certificate",
            str(cert_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert cert_path.exists()
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    assert cert["aureum_version"] == __version__
    assert cert["inputs"]["strategy"]["sha256"] == hash_file(EXAMPLE_STRATEGY)
    assert cert["inputs"]["data"]["sha256"] == hash_file(EXAMPLE_DATA)


def test_cli_writes_bundle(tmp_path: Path) -> None:
    import tarfile

    bundle_path = tmp_path / "bundle.tar.gz"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--bundle",
            str(bundle_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert bundle_path.exists()
    with tarfile.open(bundle_path, "r:gz") as tar:
        names = tar.getnames()
        assert "strategy.yaml" in names
        assert "data.csv" in names
        assert "certificate.json" in names


def test_certificate_from_dict_reconstructs_nested_dataclasses(tmp_path: Path):
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = Environment(
        aureum_version=__version__,
        git_commit="abc1234",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=env
    )

    cert_path = tmp_path / "certificate.json"
    cert_path.write_text(cert.to_json(), encoding="utf-8")

    loaded = json.loads(cert_path.read_text(encoding="utf-8"))
    reconstructed = BacktestCertificate.from_dict(loaded)
    assert reconstructed.to_dict() == cert.to_dict()
