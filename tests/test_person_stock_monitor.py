# -*- coding: utf-8 -*-
"""Regression tests for the lightweight person-stock monitor."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts import person_stock_monitor as monitor


ROOT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT_DIR / ".github/workflows/person-stock-monitor.yml"


_PERSON_MONITOR_LLM_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_API_KEYS",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "AIHUBMIX_KEY",
    "ANSPIRE_API_KEYS",
    "ANSPIRE_LLM_MODEL",
    "ANSPIRE_LLM_BASE_URL",
    "ANSPIRE_LLM_ENABLED",
    "LLM_CHANNELS",
    "LLM_OPENAI_PROTOCOL",
    "LLM_OPENAI_BASE_URL",
    "LLM_OPENAI_API_KEY",
    "LLM_OPENAI_API_KEYS",
    "LLM_OPENAI_MODELS",
    "LLM_OPENAI_ENABLED",
    "LLM_AIHUBMIX_PROTOCOL",
    "LLM_AIHUBMIX_BASE_URL",
    "LLM_AIHUBMIX_API_KEY",
    "LLM_AIHUBMIX_API_KEYS",
    "LLM_AIHUBMIX_MODELS",
    "LLM_AIHUBMIX_ENABLED",
    "LLM_ANSPIRE_PROTOCOL",
    "LLM_ANSPIRE_BASE_URL",
    "LLM_ANSPIRE_API_KEY",
    "LLM_ANSPIRE_API_KEYS",
    "LLM_ANSPIRE_MODELS",
    "LLM_ANSPIRE_ENABLED",
}


def _news_item(fingerprint: str) -> monitor.NewsItem:
    return monitor.NewsItem(
        person_label="黄仁勋",
        person_name="Jensen Huang",
        title="Nvidia CEO talks about AI hiring",
        link="https://example.test/news",
        source="Example",
        published_at="2026-06-04T00:00:00+00:00",
        summary="",
        tickers=["NVDA"],
        fingerprint=fingerprint,
    )


def _clear_llm_env(monkeypatch) -> None:
    for key in _PERSON_MONITOR_LLM_ENV_KEYS | {"LLM_PRIMARY_API_KEY", "LLM_SECONDARY_API_KEY"}:
        monkeypatch.delenv(key, raising=False)


def test_resolve_openai_config_uses_channel_mode(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_CHANNELS", "openai")
    monkeypatch.setenv("LLM_OPENAI_PROTOCOL", "openai")
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "sk-channel")
    monkeypatch.setenv("LLM_OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_OPENAI_MODELS", "gpt-5.4-mini,gpt-5.5")

    config = monitor.resolve_openai_analysis_config()

    assert config is not None
    assert config.api_key == "sk-channel"
    assert config.model == "gpt-5.4-mini"
    assert config.base_url == "https://example.test/v1"
    assert config.source == "LLM_OPENAI"


def test_resolve_openai_config_reuses_aihubmix_key(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("AIHUBMIX_KEY", "sk-aihubmix")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")

    config = monitor.resolve_openai_analysis_config()

    assert config is not None
    assert config.api_key == "sk-aihubmix"
    assert config.model == "gpt-5.5"
    assert config.base_url == "https://aihubmix.com/v1"
    assert config.source == "AIHUBMIX_KEY"


def test_resolve_openai_configs_keeps_fallback_candidates(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ANSPIRE_API_KEYS", "sk-anspire")
    monkeypatch.setenv("ANSPIRE_LLM_MODEL", "Doubao-Seed-2.0-lite")

    configs = monitor.resolve_openai_analysis_configs()

    assert [config.source for config in configs] == ["OPENAI_API_KEY", "ANSPIRE_API_KEYS"]


def test_filter_notifiable_items_skips_low_strength_low_confidence() -> None:
    low_item = _news_item("low")
    medium_item = _news_item("medium")
    analyses = {
        "low": {"impact_level": "low", "confidence": "low"},
        "medium": {"impact_level": "medium", "confidence": "low"},
    }

    result = monitor.filter_notifiable_items([low_item, medium_item], analyses)

    assert result == [medium_item]


def test_person_stock_monitor_workflow_maps_llm_env() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["monitor"]["steps"]
    monitor_step = next(step for step in steps if "FEISHU_WEBHOOK_URL" in step.get("env", {}))
    env = monitor_step["env"]

    for key in _PERSON_MONITOR_LLM_ENV_KEYS:
        assert key in env

    assert env["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert env["LLM_OPENAI_API_KEY"] == "${{ secrets.LLM_OPENAI_API_KEY }}"
    assert "vars.LLM_OPENAI_MODELS" in env["LLM_OPENAI_MODELS"]
    assert "secrets.LLM_OPENAI_MODELS" in env["LLM_OPENAI_MODELS"]
