"""Load, override, and hash strategy configs.

A loaded config has three components used by the system:
  1. The validated, normalized `StrategyConfig` object.
  2. A canonical JSON string for storage / diff / display.
  3. A short SHA256 hash that identifies this exact config in
     `backtest_runs.config_hash`. Same hash ⇒ reproducible run.

Inline overrides via `--set key.path=value` apply BEFORE validation so
override values pass through normalization (e.g., weights re-normalize).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from bloasis.config.schema import StrategyConfig


def _coerce_scalar(raw: str) -> Any:
    """Best-effort coerce a CLI string value to int / float / bool / str."""
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none", "~"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _set_nested(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set `data[a][b][c] = value` from a dotted path 'a.b.c'.

    Creates intermediate dicts if missing. Raises if path traverses a
    non-dict node, since that signals a malformed override against schema.
    """
    parts = dotted_key.split(".")
    cursor: dict[str, Any] = data
    for key in parts[:-1]:
        existing = cursor.get(key)
        if existing is None:
            new: dict[str, Any] = {}
            cursor[key] = new
            cursor = new
        elif isinstance(existing, dict):
            cursor = existing
        else:
            raise ValueError(f"--set path '{dotted_key}' traverses non-dict node at '{key}'")
    cursor[parts[-1]] = value


def resolve_overrides(raw: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Apply CLI `key.path=value` overrides to a raw YAML dict.

    Returns a new dict; does not mutate input.
    """
    if not overrides:
        return raw

    out: dict[str, Any] = _deep_copy(raw)
    for spec in overrides:
        if "=" not in spec:
            raise ValueError(f"--set value must be 'key.path=value', got: {spec!r}")
        key, _, value_str = spec.partition("=")
        _set_nested(out, key.strip(), _coerce_scalar(value_str.strip()))
    return out


def _deep_copy(data: Any) -> Any:
    """Recursive copy for YAML-shaped data (dicts, lists, scalars)."""
    if isinstance(data, dict):
        return {k: _deep_copy(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_deep_copy(v) for v in data]
    return data


def load_config(path: Path, overrides: list[str] | None = None) -> StrategyConfig:
    """Load a YAML config, apply inline overrides, validate, return."""
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping, got {type(raw).__name__}")

    raw = resolve_overrides(raw, overrides or [])
    return StrategyConfig.model_validate(raw)


def config_hash(config: StrategyConfig) -> str:
    """Short stable hash of a validated config.

    Used as `backtest_runs.config_hash`. Two configs with the same hash are
    guaranteed to produce the same backtest (modulo data sources).

    Hash is invariant to YAML key order: we serialize the validated dict
    with `sort_keys=True` so any free-form dict fields (e.g. regime
    multipliers) hash identically regardless of input file ordering.
    """
    payload = config.model_dump(mode="json", exclude_none=False)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:12]
