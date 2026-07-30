"""Tests for the Aureum AI client wrapper."""

from __future__ import annotations

import pytest

from aureum.ai import AnthropicClient, _extract_yaml


def test_extract_yaml_from_fenced_block():
    text = "Some prose.\n\n```yaml\napiVersion: aureum.io/v1alpha1\nkind: Strategy\n```"
    assert _extract_yaml(text) == "apiVersion: aureum.io/v1alpha1\nkind: Strategy"


def test_extract_yaml_bare_yaml():
    text = "apiVersion: aureum.io/v1alpha1\nkind: Strategy"
    assert _extract_yaml(text) == text


def test_extract_yaml_missing_yaml_raises():
    with pytest.raises(ValueError, match="No YAML block found"):
        _extract_yaml("Just prose, no code.")


def test_anthropic_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient()
