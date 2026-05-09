"""Tests for cohen-malloy text-diff signal."""

from __future__ import annotations

import math

import pytest

from bloasis.scoring.edgar_textdiff import (
    cosine_similarity,
    length_change_pct,
    tokenize,
)


def test_tokenize_drops_stopwords_and_short_words() -> None:
    text = "The Company has business operations in many countries and faces risks."
    tokens = tokenize(text)
    # Length >= 4, lowercased, stopwords removed
    assert "company" not in tokens  # stopword
    assert "business" not in tokens  # stopword
    assert "operations" not in tokens  # stopword
    assert "countries" in tokens
    assert "faces" in tokens
    assert "risks" in tokens
    # No short words
    assert all(len(t) >= 4 for t in tokens)


def test_cosine_identical_text_returns_one() -> None:
    text = "Supply chain disruptions could materially affect revenue and margins."
    assert cosine_similarity(text, text) == pytest.approx(1.0)


def test_cosine_disjoint_returns_zero() -> None:
    a = "supply chain disruptions"
    b = "litigation regulatory penalties"
    assert cosine_similarity(a, b) == 0.0


def test_cosine_nan_on_empty_input() -> None:
    assert math.isnan(cosine_similarity("", "some text"))
    assert math.isnan(cosine_similarity("some text", ""))


def test_cosine_partial_overlap_in_unit_range() -> None:
    a = "supply chain risks regulatory uncertainty"
    b = "supply chain risks competitive pressure"
    sim = cosine_similarity(a, b)
    assert 0.0 < sim < 1.0


def test_length_change_pct() -> None:
    assert length_change_pct("a" * 110, "a" * 100) == 0.10
    assert length_change_pct("a" * 80, "a" * 100) == -0.20
    assert math.isnan(length_change_pct("a" * 100, ""))
