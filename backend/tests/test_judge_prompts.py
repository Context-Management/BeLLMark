from app.core.judges import COMPARISON_PROMPT, SEPARATE_PROMPT, SCORING_RUBRIC


def test_comparison_prompt_has_verbosity_normalization():
    assert "length" in COMPARISON_PROMPT.lower() or "verbosity" in COMPARISON_PROMPT.lower()


def test_separate_prompt_has_verbosity_normalization():
    assert "length" in SEPARATE_PROMPT.lower() or "verbosity" in SEPARATE_PROMPT.lower()


def test_scoring_rubric_defines_all_ten_levels():
    """Every score 1-10 must have a verbal anchor in the rubric."""
    for score in range(1, 11):
        assert f"{score} -" in SCORING_RUBRIC or f"{score:2d} -" in SCORING_RUBRIC


def test_scoring_rubric_is_criterion_agnostic():
    """Rubric must not reference any specific criterion name."""
    specific_criteria = ["accuracy", "clarity", "coherence", "relevance", "creativity"]
    rubric_lower = SCORING_RUBRIC.lower()
    for name in specific_criteria:
        assert name not in rubric_lower, f"Rubric should not reference specific criterion '{name}'"


def test_comparison_prompt_includes_rubric():
    """Comparison prompt must contain the full scoring rubric."""
    assert "Scoring Scale" in COMPARISON_PROMPT
    assert "Exemplary" in COMPARISON_PROMPT
    assert "Failing" in COMPARISON_PROMPT


def test_separate_prompt_includes_rubric():
    """Separate prompt must contain the full scoring rubric."""
    assert "Scoring Scale" in SEPARATE_PROMPT
    assert "Exemplary" in SEPARATE_PROMPT
    assert "Failing" in SEPARATE_PROMPT


def test_rubric_appears_before_task_section_in_comparison():
    """Rubric must appear between criteria and the task instructions."""
    rubric_pos = COMPARISON_PROMPT.index("Scoring Scale")
    task_pos = COMPARISON_PROMPT.index("Your Task")
    criteria_pos = COMPARISON_PROMPT.index("Evaluation Criteria")
    assert criteria_pos < rubric_pos < task_pos


def test_rubric_appears_before_task_section_in_separate():
    """Rubric must appear between criteria and the task instructions."""
    rubric_pos = SEPARATE_PROMPT.index("Scoring Scale")
    task_pos = SEPARATE_PROMPT.index("Your Task")
    criteria_pos = SEPARATE_PROMPT.index("Evaluation Criteria")
    assert criteria_pos < rubric_pos < task_pos
