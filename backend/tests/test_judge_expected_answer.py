"""Tests for expected_answer injection into judge prompts."""


class TestExpectedAnswerPromptInjection:
    def test_comparison_prompt_includes_expected_answer_param(self):
        import inspect
        from app.core.judges import judge_comparison
        sig = inspect.signature(judge_comparison)
        assert 'expected_answer' in sig.parameters

    def test_separate_prompt_includes_expected_answer_param(self):
        import inspect
        from app.core.judges import judge_separate
        sig = inspect.signature(judge_separate)
        assert 'expected_answer' in sig.parameters

    def test_comparison_prompt_without_expected_answer(self):
        from app.core.judges import build_judge_prompt_comparison
        prompt = build_judge_prompt_comparison(
            system_prompt="sys", user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            responses_text="Response 1: hello",
            response_count=1,
            expected_answer=None
        )
        assert "Reference Answer" not in prompt

    def test_comparison_prompt_requires_score_rationales(self):
        from app.core.judges import build_judge_prompt_comparison
        prompt = build_judge_prompt_comparison(
            system_prompt="sys",
            user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            responses_text="Response 1: hello",
            response_count=1,
            expected_answer=None,
        )
        assert '"score_rationales":' in prompt
        assert '"score_rationale":' not in prompt


    def test_comparison_prompt_with_expected_answer(self):
        from app.core.judges import build_judge_prompt_comparison
        prompt = build_judge_prompt_comparison(
            system_prompt="sys", user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            responses_text="Response 1: hello",
            response_count=1,
            expected_answer="The correct answer is 42."
        )
        assert "Reference Answer" in prompt
        assert "The correct answer is 42." in prompt
        assert "reference point, not as the only correct answer" in prompt

    def test_separate_prompt_with_expected_answer(self):
        from app.core.judges import build_judge_prompt_separate
        prompt = build_judge_prompt_separate(
            system_prompt="sys", user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            response_text="hello world",
            expected_answer="The expected response."
        )
        assert "Reference Answer" in prompt
        assert "The expected response." in prompt

    def test_separate_prompt_without_expected_answer(self):
        from app.core.judges import build_judge_prompt_separate
        prompt = build_judge_prompt_separate(
            system_prompt="sys", user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            response_text="hello world",
            expected_answer=None
        )
        assert "Reference Answer" not in prompt


    def test_separate_prompt_requires_score_rationale(self):
        from app.core.judges import build_judge_prompt_separate
        prompt = build_judge_prompt_separate(
            system_prompt="sys",
            user_prompt="usr",
            criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            response_text="hello world",
            expected_answer=None,
        )
        assert '"score_rationale":' in prompt
        assert '"score_rationales":' not in prompt
