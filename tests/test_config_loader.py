"""Tests for `bloasis.config.loader`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bloasis.config import StrategyConfig, config_hash, load_config, resolve_overrides

# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_baseline(baseline_config_path: Path) -> None:
    cfg = load_config(baseline_config_path)
    assert isinstance(cfg, StrategyConfig)
    assert cfg.universe.source == "sp500"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_load_non_mapping_root_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config(bad)


def test_load_unknown_section_rejected(tmp_path: Path) -> None:
    from pydantic import ValidationError

    bad = tmp_path / "extra.yaml"
    bad.write_text("universe:\n  source: sp500\nbogus_section: 1\n")
    with pytest.raises(ValidationError):
        load_config(bad)


# ---------------------------------------------------------------------------
# resolve_overrides
# ---------------------------------------------------------------------------


def test_overrides_dotted_scalar(baseline_raw: dict) -> None:
    out = resolve_overrides(baseline_raw, ["universe.source=sp500_historical"])
    assert out["universe"]["source"] == "sp500_historical"
    # original unchanged (defensive copy)
    assert baseline_raw["universe"]["source"] == "sp500"


def test_overrides_creates_intermediate_dicts() -> None:
    out = resolve_overrides({}, ["a.b.c=42"])
    assert out == {"a": {"b": {"c": 42}}}


def test_overrides_coerces_int_float_bool_null() -> None:
    out = resolve_overrides(
        {},
        [
            "scorer.weights.momentum=0.25",
            "scorer.entry_threshold=0.7",
            "execution.fees_bps=2",
            "execution.fill_mode=market",
            "scorer.ml_model_path=null",
            "universe.dummy_bool=true",
        ],
    )
    assert out["scorer"]["weights"]["momentum"] == 0.25
    assert out["scorer"]["entry_threshold"] == 0.7
    assert out["execution"]["fees_bps"] == 2
    assert out["execution"]["fill_mode"] == "market"
    assert out["scorer"]["ml_model_path"] is None
    assert out["universe"]["dummy_bool"] is True


def test_overrides_invalid_format_rejected() -> None:
    with pytest.raises(ValueError, match="must be 'key.path=value'"):
        resolve_overrides({}, ["no_equals_sign"])


def test_overrides_traversal_through_non_dict_rejected() -> None:
    with pytest.raises(ValueError, match="non-dict node"):
        resolve_overrides({"a": 1}, ["a.b=2"])


def test_load_with_overrides(baseline_config_path: Path) -> None:
    cfg = load_config(
        baseline_config_path,
        overrides=["scorer.weights.momentum=0.30", "execution.fees_bps=2"],
    )
    # Weights re-normalize after override; momentum should be largest non-original weight
    weights = cfg.scorer.weights.model_dump()
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert weights["momentum"] > weights["technical"]
    assert cfg.execution.fees_bps == 2


def test_load_invalid_override_fails_validation(baseline_config_path: Path) -> None:
    # Setting exit >= entry should fail validation post-override
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(
            baseline_config_path,
            overrides=["scorer.exit_threshold=0.99"],
        )


# ---------------------------------------------------------------------------
# config_hash — determinism + sensitivity
# ---------------------------------------------------------------------------


def test_hash_stable_for_same_config(baseline_config_path: Path) -> None:
    h1 = config_hash(load_config(baseline_config_path))
    h2 = config_hash(load_config(baseline_config_path))
    assert h1 == h2
    assert len(h1) == 12


def test_hash_changes_when_value_changes(baseline_config_path: Path) -> None:
    h1 = config_hash(load_config(baseline_config_path))
    h2 = config_hash(load_config(baseline_config_path, overrides=["execution.fees_bps=2"]))
    assert h1 != h2


def test_hash_invariant_to_yaml_key_order(
    tmp_path: Path,
    baseline_raw: dict,
) -> None:
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(yaml.safe_dump(baseline_raw, sort_keys=False))
    # write same data with sorted keys to verify hash invariance
    b.write_text(yaml.safe_dump(baseline_raw, sort_keys=True))
    h_a = config_hash(load_config(a))
    h_b = config_hash(load_config(b))
    assert h_a == h_b
