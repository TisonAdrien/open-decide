"""Tests for context truncation."""

from __future__ import annotations

from open_decide.context import DEFAULT_MAX_CHARS, truncate_context


def test_short_text_unchanged() -> None:
    assert truncate_context("hello", 100) == "hello"


def test_disabled_truncation() -> None:
    text = "x" * 10000
    assert truncate_context(text, 0) == text
    assert truncate_context(text, -1) == text


def test_head_and_tail_kept() -> None:
    text = "START" + ("a" * 5000) + "END"
    out = truncate_context(text, 500)
    assert len(out) <= 500 + len("\n\n[... truncated ...]\n\n") + 100
    assert out.startswith("START")
    assert out.endswith("END")
    assert "[... truncated ...]" in out


def test_default_budget() -> None:
    text = "x" * (DEFAULT_MAX_CHARS + 1000)
    out = truncate_context(text)
    # Head 70%, tail 30%, separator in the middle.
    assert len(out) <= DEFAULT_MAX_CHARS + 10
