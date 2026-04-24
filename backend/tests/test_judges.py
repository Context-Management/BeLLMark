# backend/tests/test_judges.py
import json
import re
import random
import pytest
from app.core.judges import build_scores_template, build_comments_template, remap_criterion_keys, extract_json, _repair_json, _try_close_truncated_json, create_blind_mapping


def test_build_scores_template_uses_actual_criteria_names():
    """Template should use actual criteria names, not criterion1/criterion2."""
    criteria = [
        {"name": "Accuracy", "description": "test", "weight": 1},
        {"name": "Clarity", "description": "test", "weight": 1},
    ]
    labels = ["A", "B", "C"]
    template = build_scores_template(criteria, labels)

    # Should contain actual criteria names
    assert "Accuracy" in template
    assert "Clarity" in template

    # Should NOT contain placeholder names
    assert "criterion1" not in template
    assert "criterion2" not in template


def test_build_scores_template_includes_all_labels():
    """Template should include all response labels."""
    criteria = [
        {"name": "Accuracy", "description": "test", "weight": 1},
    ]
    labels = ["A", "B", "C"]
    template = build_scores_template(criteria, labels)

    assert "A" in template
    assert "B" in template
    assert "C" in template


def test_remap_criterionN_to_actual_names():
    """Should remap criterion1, criterion2 to actual criteria names."""
    criteria = [
        {"name": "Accuracy", "description": "test", "weight": 1},
        {"name": "Clarity", "description": "test", "weight": 1},
    ]
    scores = {"criterion1": 8, "criterion2": 7}
    result = remap_criterion_keys(scores, criteria)

    assert result == {"Accuracy": 8, "Clarity": 7}


def test_remap_criterion_keys_preserves_existing_names():
    """Should preserve scores that already use correct names."""
    criteria = [
        {"name": "Accuracy", "description": "test", "weight": 1},
        {"name": "Clarity", "description": "test", "weight": 1},
    ]
    scores = {"Accuracy": 8, "Clarity": 7}
    result = remap_criterion_keys(scores, criteria)

    # Should return unchanged
    assert result == {"Accuracy": 8, "Clarity": 7}


def test_remap_criterion_keys_handles_mixed_format():
    """Should handle mix of criterionN and actual names."""
    criteria = [
        {"name": "Accuracy", "description": "test", "weight": 1},
        {"name": "Clarity", "description": "test", "weight": 1},
        {"name": "Relevance", "description": "test", "weight": 1},
    ]
    scores = {"criterion1": 8, "Clarity": 7, "criterion3": 9}
    result = remap_criterion_keys(scores, criteria)

    assert result == {"Accuracy": 8, "Clarity": 7, "Relevance": 9}


def test_build_comments_template():
    """Template should include comment structure for each label."""
    labels = ["A", "B"]
    template = build_comments_template(labels)
    assert '"A"' in template
    assert '"B"' in template
    assert '"text"' in template
    assert '"sentiment"' in template


def test_extract_json_with_comments():
    """extract_json should handle response with comments field."""
    text = '''```json
    {
        "ranking": ["A", "B"],
        "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}},
        "comments": {
            "A": [
                {"text": "Well structured", "sentiment": "positive"},
                {"text": "Good examples", "sentiment": "positive"},
                {"text": "Minor typo", "sentiment": "negative"},
                {"text": "Clear explanation", "sentiment": "positive"},
                {"text": "Could be more concise", "sentiment": "negative"}
            ],
            "B": [
                {"text": "Misses key point", "sentiment": "negative"},
                {"text": "Good formatting", "sentiment": "positive"},
                {"text": "Incomplete answer", "sentiment": "negative"},
                {"text": "Uses relevant terms", "sentiment": "positive"},
                {"text": "Lacks depth", "sentiment": "negative"}
            ]
        },
        "reasoning": "A is better"
    }
    ```'''
    result = extract_json(text)
    assert "comments" in result
    assert len(result["comments"]["A"]) == 5
    assert result["comments"]["A"][0]["sentiment"] in ("positive", "negative")


class TestRepairJson:
    """Tests for _repair_json handling various LLM output quirks."""

    def test_trailing_commas(self):
        text = '{"a": 1, "b": 2,}'
        assert json.loads(_repair_json(text)) == {"a": 1, "b": 2}

    def test_single_line_comments(self):
        text = '{"a": 1, // this is a comment\n"b": 2}'
        assert json.loads(_repair_json(text)) == {"a": 1, "b": 2}

    def test_multi_line_comments(self):
        text = '{"a": 1, /* multi\nline\ncomment */ "b": 2}'
        assert json.loads(_repair_json(text)) == {"a": 1, "b": 2}

    def test_nan_infinity(self):
        text = '{"a": NaN, "b": Infinity, "c": -Infinity}'
        result = json.loads(_repair_json(text))
        assert result == {"a": None, "b": None, "c": None}

    def test_undefined(self):
        text = '{"a": undefined}'
        result = json.loads(_repair_json(text))
        assert result == {"a": None}

    def test_unquoted_keys(self):
        text = '{ranking: [1, 2], scores: {"1": 8}}'
        result = json.loads(_repair_json(text))
        assert result["ranking"] == [1, 2]
        assert result["scores"] == {"1": 8}

    def test_control_characters_stripped(self):
        text = '{"a": "hello\x00world"}'
        result = json.loads(_repair_json(text))
        assert result == {"a": "helloworld"}

    def test_combined_issues(self):
        text = '{ranking: [1, 2,], // best first\nscores: {}, /* end */}'
        result = json.loads(_repair_json(text))
        assert result["ranking"] == [1, 2]


class TestExtractJsonEdgeCases:
    """Tests for extract_json handling Gemini-specific edge cases."""

    def test_uppercase_json_code_block(self):
        text = '```JSON\n{"ranking": [1, 2], "reasoning": "test"}\n```'
        result = extract_json(text)
        assert result["ranking"] == [1, 2]

    def test_json_embedded_in_explanation(self):
        text = '''Here is my evaluation:

{"ranking": [1, 2, 3], "scores": {"1": {"Quality": 8}, "2": {"Quality": 7}, "3": {"Quality": 6}}, "reasoning": "Response 1 is best"}

I hope this helps!'''
        result = extract_json(text)
        assert result["ranking"] == [1, 2, 3]

    def test_json_with_trailing_commas_in_code_block(self):
        text = '```json\n{"ranking": [1, 2,], "reasoning": "test",}\n```'
        result = extract_json(text)
        assert result["ranking"] == [1, 2]

    def test_json_with_unquoted_keys_in_response(self):
        text = '{ranking: [1, 2], scores: {"1": {"Quality": 8}, "2": {"Quality": 7}}, reasoning: "test"}'
        result = extract_json(text)
        assert result["ranking"] == [1, 2]
        assert result["reasoning"] == "test"

    def test_truncated_json_recovery(self):
        """Simulate a model hitting max tokens mid-JSON."""
        text = '{"ranking": [1, 2, 3], "scores": {"1": {"Quality": 8}, "2": {"Quality": 7'
        result = extract_json(text)
        assert result["ranking"] == [1, 2, 3]

    def test_truncated_json_with_string_value(self):
        text = '{"ranking": [1, 2], "reasoning": "Response 1 excels because'
        result = extract_json(text)
        assert result["ranking"] == [1, 2]

    def test_multiple_json_objects_returns_largest(self):
        text = 'Small: {"a": 1}\nLarge: {"ranking": [1, 2], "scores": {"1": 8}, "reasoning": "test"}'
        result = extract_json(text)
        assert "ranking" in result  # Should pick the larger JSON

    def test_json_with_multiline_comments(self):
        text = '''{"ranking": [1, 2],
/* These scores reflect quality */
"scores": {"1": {"Quality": 8}, "2": {"Quality": 7}},
"reasoning": "test"}'''
        result = extract_json(text)
        assert result["ranking"] == [1, 2]

    def test_empty_response_raises(self):
        with pytest.raises(ValueError, match="Empty response"):
            extract_json("")

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            extract_json("This response contains no JSON at all.")

    def test_nan_in_scores(self):
        text = '{"ranking": [1, 2], "scores": {"1": {"Quality": NaN}, "2": {"Quality": 8}}, "reasoning": "test"}'
        result = extract_json(text)
        assert result["scores"]["1"]["Quality"] is None
        assert result["scores"]["2"]["Quality"] == 8


class TestTryCloseTruncatedJson:
    """Tests for _try_close_truncated_json."""

    def test_closes_single_brace(self):
        text = '{"a": 1, "b": 2'
        result = _try_close_truncated_json(text)
        assert json.loads(result) == {"a": 1, "b": 2}

    def test_closes_nested_braces(self):
        text = '{"a": {"b": 1'
        result = _try_close_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["a"]["b"] == 1

    def test_closes_array_and_brace(self):
        text = '{"ranking": [1, 2'
        result = _try_close_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["ranking"] == [1, 2]

    def test_already_balanced(self):
        text = '{"a": 1}'
        result = _try_close_truncated_json(text)
        assert result == text

    def test_handles_strings_with_braces(self):
        text = '{"a": "hello {world"'
        result = _try_close_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["a"] == "hello {world"


@pytest.mark.asyncio
async def test_summarize_judge_comments_formats_prompt():
    """summarize_judge_comments should format comments into a summarization prompt."""
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_preset = MagicMock()
    mock_preset.name = "TestJudge"

    comments_by_model = {
        "ModelA": [
            {"text": "Clear structure", "sentiment": "positive"},
            {"text": "Good examples", "sentiment": "positive"},
            {"text": "Verbose at times", "sentiment": "negative"},
        ],
        "ModelB": [
            {"text": "Misses key points", "sentiment": "negative"},
            {"text": "Good formatting", "sentiment": "positive"},
        ],
    }

    with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = {
            "success": True,
            "content": '{"ModelA": "ModelA shows clear structure with good examples but can be verbose.", "ModelB": "ModelB has good formatting but misses key points."}',
            "tokens": 50,
        }

        from app.core.judges import summarize_judge_comments
        result = await summarize_judge_comments(mock_preset, comments_by_model)

        assert result["success"] is True
        assert "ModelA" in result["summaries"]
        assert "ModelB" in result["summaries"]
        # Verify generate was called with the judge preset
        mock_gen.assert_called_once()
        call_args = mock_gen.call_args
        assert call_args[0][0] == mock_preset  # First positional arg is preset


@pytest.mark.asyncio
async def test_summarize_judge_comments_handles_failure():
    """summarize_judge_comments should return graceful failure."""
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_preset = MagicMock()
    comments = {"ModelA": [{"text": "test", "sentiment": "positive"}]}

    with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = {"success": False, "error": "API timeout"}

        from app.core.judges import summarize_judge_comments
        result = await summarize_judge_comments(mock_preset, comments)

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
async def test_summarize_judge_comments_empty_input():
    """summarize_judge_comments should handle empty input gracefully."""
    from unittest.mock import MagicMock
    from app.core.judges import summarize_judge_comments

    mock_preset = MagicMock()
    result = await summarize_judge_comments(mock_preset, {})

    assert result["success"] is True
    assert result["summaries"] == {}


class TestRankingPermutation:
    """Ranking validation should enforce exact permutation (length, uniqueness, completeness)."""

    @pytest.mark.asyncio
    async def test_rejects_duplicate_rankings(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        # Judge returns duplicate rankings: "A" appears twice
        mock_response = '{"ranking": ["A", "A", "B"], "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}, "C": {"Accuracy": 7}}, "comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "ok", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, "score_rationales": {"A": "good", "B": "ok", "C": "fine"}, "reasoning": "test"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "duplicate" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_incomplete_rankings(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        # Judge returns only 2 rankings for 3 models
        mock_response = '{"ranking": ["A", "B"], "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}, "C": {"Accuracy": 7}}, "comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "ok", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, "score_rationales": {"A": "good", "B": "ok", "C": "fine"}, "reasoning": "test"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "3" in result["error"]  # expected 3

    @pytest.mark.asyncio
    async def test_accepts_valid_permutation(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = '{"ranking": ["B", "A", "C"], "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 9}, "C": {"Accuracy": 6}}, "comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "better", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, "score_rationales": {"A": "good", "B": "better", "C": "fine"}, "reasoning": "B is best"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert "rankings" in result


    @pytest.mark.asyncio
    async def test_accepts_lowercase_and_whitespace_ranking_labels(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = (
            '{"ranking": [" a ", "b", " C "], '
            '"scores": {'
            '"A": {"Accuracy": 9}, '
            '"B": {"Accuracy": 8}, '
            '"C": {"Accuracy": 7}}, '
            '"comments": {'
            '"A": [{"text": "A note", "sentiment": "positive"}], '
            '"B": [{"text": "B note", "sentiment": "positive"}], '
            '"C": [{"text": "C note", "sentiment": "positive"}]}, '
            '"score_rationales": {'
            '"A": "A rationale", '
            '"B": "B rationale", '
            '"C": "C rationale"}, '
            '"reasoning": "test"}'
        )
        fixed_mapping = {"A": 11, "B": 22, "C": 33}

        with patch("app.core.judges.create_blind_mapping", return_value=fixed_mapping),              patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {11: "A content", 22: "B content", 33: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert result["rankings"] == ["A", "B", "C"]


class TestComparisonScoreRationales:
    @pytest.mark.asyncio
    async def test_accepts_score_rationales_keyed_by_blind_labels(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = (
            '{"ranking": ["B", "A", "C"], '
            '"scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 9}, "C": {"Accuracy": 6}}, '
            '"comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "better", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, '
            '"score_rationales": {"A": "strong answer", "B": "best answer", "C": "weaker answer"}, '
            '"reasoning": "2 is best"}'
        )

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert set(result["score_rationales"].keys()) == {10, 20, 30}
        assert set(result["comments"].keys()) == {10, 20, 30}
        assert any(comment[0]["text"] == "good" for comment in result["comments"].values())


    @pytest.mark.asyncio
    async def test_accepts_score_rationales_for_four_models(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = (
            '{"ranking": ["D", "C", "B", "A"], '
            '"scores": {'
            '"A": {"Accuracy": 6}, '
            '"B": {"Accuracy": 7}, '
            '"C": {"Accuracy": 8}, '
            '"D": {"Accuracy": 9}}, '
            '"comments": {'
            '"A": [{"text": "A note", "sentiment": "negative"}], '
            '"B": [{"text": "B note", "sentiment": "positive"}], '
            '"C": [{"text": "C note", "sentiment": "positive"}], '
            '"D": [{"text": "D note", "sentiment": "positive"}]}, '
            '"score_rationales": {'
            '"A": "A rationale", '
            '"B": "B rationale", '
            '"C": "C rationale", '
            '"D": "D rationale"}, '
            '"reasoning": "D is best"}'
        )
        fixed_mapping = {"A": 101, "B": 102, "C": 103, "D": 104}

        with patch("app.core.judges.create_blind_mapping", return_value=fixed_mapping),              patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {101: "A content", 102: "B content", 103: "C content", 104: "D content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert set(result["score_rationales"].keys()) == {101, 102, 103, 104}
        assert result["score_rationales"][104] == "D rationale"
        assert result["score_rationales"][103] == "C rationale"
        assert result["score_rationales"][102] == "B rationale"
        assert result["score_rationales"][101] == "A rationale"


    @pytest.mark.asyncio
    async def test_accepts_lowercase_and_whitespace_blind_labels_in_score_rationales(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = (
            '{"ranking": ["A", "B", "C"], '
            '"scores": {'
            '"A": {"Accuracy": 9}, '
            '"B": {"Accuracy": 8}, '
            '"C": {"Accuracy": 7}}, '
            '"comments": {'
            '"A": [{"text": "A note", "sentiment": "positive"}], '
            '"B": [{"text": "B note", "sentiment": "positive"}], '
            '"C": [{"text": "C note", "sentiment": "positive"}]}, '
            '"score_rationales": {'
            '" a ": "A rationale", '
            '"b": "B rationale", '
            '" C ": "C rationale"}, '
            '"reasoning": "test"}'
        )
        fixed_mapping = {"A": 11, "B": 22, "C": 33}

        with patch("app.core.judges.create_blind_mapping", return_value=fixed_mapping),              patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {11: "A content", 22: "B content", 33: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert result["score_rationales"] == {11: "A rationale", 22: "B rationale", 33: "C rationale"}

    @pytest.mark.asyncio
    async def test_rejects_missing_score_rationales(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = '{"ranking": ["A", "B", "C"], "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}, "C": {"Accuracy": 7}}, "comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "ok", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, "reasoning": "test"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "score_rationales" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_singular_score_rationale_in_comparison_mode(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = '{"ranking": ["A", "B", "C"], "scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}, "C": {"Accuracy": 7}}, "comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "ok", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, "score_rationale": "wrong key", "reasoning": "test"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "score_rationales" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_unknown_blind_labels_in_score_rationales(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_comparison

        mock_preset = MagicMock()
        mock_response = (
            '{"ranking": ["A", "B", "C"], '
            '"scores": {"A": {"Accuracy": 8}, "B": {"Accuracy": 6}, "C": {"Accuracy": 7}}, '
            '"comments": {"A": [{"text": "good", "sentiment": "positive"}], "B": [{"text": "ok", "sentiment": "positive"}], "C": [{"text": "fine", "sentiment": "positive"}]}, '
            '"score_rationales": {"A": "ok", "B": "ok", "D": "unknown"}, '
            '"reasoning": "test"}'
        )

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_comparison(
                mock_preset, "system", "user",
                {10: "A content", 20: "B content", 30: "C content"},
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "score_rationales" in result["error"]



class TestSeparateScoreRationaleParsing:
    @pytest.mark.asyncio
    async def test_accepts_singular_score_rationale(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_separate

        mock_preset = MagicMock()
        mock_response = (
            '{"scores": {"Accuracy": 9}, '
            '"comments": [{"text": "good", "sentiment": "positive"}], '
            '"score_rationale": "Clear, concise, and fully accurate.", '
            '"reasoning": "test"}'
        )

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_separate(
                mock_preset, "system", "user",
                "response text",
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is True
        assert result["score_rationale"] == "Clear, concise, and fully accurate."
        assert result["scores"] == {"Accuracy": 9}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("score_rationale", [None, "   "])
    async def test_rejects_missing_or_blank_score_rationale(self, score_rationale):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_separate

        mock_preset = MagicMock()
        if score_rationale is None:
            mock_response = '{"scores": {"Accuracy": 9}, "comments": [], "reasoning": "test"}'
        else:
            mock_response = '{"scores": {"Accuracy": 9}, "comments": [], "score_rationale": "   ", "reasoning": "test"}'

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_separate(
                mock_preset, "system", "user",
                "response text",
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "score_rationale" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_plural_score_rationales_in_separate_mode(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.judges import judge_separate

        mock_preset = MagicMock()
        mock_response = (
            '{"scores": {"Accuracy": 9}, '
            '"comments": [], '
            '"score_rationales": {"A": "oops"}, '
            '"reasoning": "test"}'
        )

        with patch("app.core.judges.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"success": True, "content": mock_response}
            result = await judge_separate(
                mock_preset, "system", "user",
                "response text",
                [{"name": "Accuracy", "description": "test", "weight": 1}]
            )

        assert result["success"] is False
        assert "score_rationale" in result["error"]


class TestPositionBias:
    def test_blind_mapping_randomizes_labels(self):
        """Blind mapping should assign random labels to models."""
        model_ids = [1, 2, 3]
        # Run multiple times and check we get different orderings
        orderings = set()
        for _ in range(20):
            mapping = create_blind_mapping(model_ids)
            ordering = tuple(mapping[label] for label in sorted(mapping.keys()))
            orderings.add(ordering)
        # With 3 models and 20 attempts, should see at least 2 different orderings
        assert len(orderings) >= 2, "Blind mapping should produce different orderings"

    def test_presentation_order_randomizes_content(self):
        """The MODEL CONTENT at each position should vary across calls.

        The presentation labels (1, 2, 3) are always sequential — that's fine.
        What matters is which model's content appears at position 1. If position
        bias exists in the LLM judge, randomizing which content is shown first
        prevents any single model from systematically benefiting.
        """
        from app.core.judges import _build_comparison_responses

        generations = {
            10: "UNIQUE_CONTENT_MODEL_10",
            20: "UNIQUE_CONTENT_MODEL_20",
            30: "UNIQUE_CONTENT_MODEL_30",
        }
        blind_mapping = {"A": 10, "B": 20, "C": 30}

        # Track which model's content appears in the first position
        first_position_contents = set()
        for _ in range(30):
            text, mapping = _build_comparison_responses(generations, blind_mapping)
            # Extract content shown in "Response 1" position
            # Format: "**Response 1 (A):**\n<content>\n\n**Response 2 (B):**..."
            match = re.search(r'\*\*Response 1 \([A-Z]\):\*\*\n(.+?)(?:\n\n\*\*Response|\Z)', text, re.DOTALL)
            assert match, "Should contain Response 1 block with blind label"
            first_position_contents.add(match.group(1).strip())

        assert len(first_position_contents) >= 2, \
            "Content at position 1 must vary across calls (randomized presentation order)"

    def test_presentation_to_blind_mapping_is_valid(self):
        """The mapping from presentation labels to blind labels should be complete."""
        from app.core.judges import _build_comparison_responses

        generations = {10: "Content A", 20: "Content B", 30: "Content C"}
        blind_mapping = {"A": 10, "B": 20, "C": 30}

        text, pres_to_blind = _build_comparison_responses(generations, blind_mapping)
        # Should have entries for all presentation labels
        assert set(pres_to_blind.keys()) == {"1", "2", "3"}
        # Should map to valid blind labels
        assert set(pres_to_blind.values()) == {"A", "B", "C"}
