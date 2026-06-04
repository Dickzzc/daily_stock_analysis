# -*- coding: utf-8 -*-
"""Static checks for scheduled daily analysis mode."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT_DIR / ".github/workflows/00-daily-analysis.yml"


def _load_analyze_step() -> dict:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["analyze"]["steps"]
    return next(step for step in steps if "SCHEDULE_MODE" in step.get("env", {}))


def test_schedule_defaults_to_market_review_only() -> None:
    step = _load_analyze_step()

    assert step["env"]["SCHEDULE_MODE"].endswith("|| 'market-only' }}")
    assert 'MODE="${{ github.event.inputs.mode || \'\' }}"' in step["run"]
    assert 'MODE="$SCHEDULE_MODE"' in step["run"]
    assert "python main.py --market-review $FORCE_RUN_ARG" in step["run"]
