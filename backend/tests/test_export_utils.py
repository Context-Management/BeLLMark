"""Unit tests for export utility functions in common.py."""
from app.core.exports.common import truncate_text, MAX_QUESTION_DISPLAY_CHARS


def test_truncate_text_short():
    assert truncate_text("Hello world", 300) == "Hello world"


def test_truncate_text_long():
    long = "x" * 500
    result = truncate_text(long, 300)
    assert len(result) == 303  # 300 + "..."
    assert result.endswith("...")


def test_truncate_text_exact():
    exact = "x" * 300
    assert truncate_text(exact, 300) == exact


def test_max_question_display_chars():
    assert MAX_QUESTION_DISPLAY_CHARS == 300


def test_truncate_text_empty():
    assert truncate_text("", 300) == ""


def test_truncate_text_none():
    assert truncate_text(None, 300) == ""


def test_truncate_text_default_max():
    long = "y" * 500
    result = truncate_text(long)
    assert len(result) == 303
    assert result.endswith("...")
