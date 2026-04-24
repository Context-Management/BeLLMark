from app.core.judges import detect_family_overlap


def test_family_overlap_detected():
    """Detects family overlap between GPT judge and GPT model."""
    warnings = detect_family_overlap("gpt-4o", ["gpt-4-turbo", "claude-3.5-sonnet"])
    assert len(warnings) == 1
    assert warnings[0]["family"] == "openai"


def test_no_overlap_cross_family():
    """No warning when judge and models are from different families."""
    warnings = detect_family_overlap("claude-3.5-sonnet", ["gpt-4o", "gemini-pro"])
    assert len(warnings) == 0


def test_unknown_model_no_warning():
    """Unknown models don't trigger false positive warnings."""
    warnings = detect_family_overlap("custom-model", ["gpt-4o"])
    assert len(warnings) == 0


def test_glm_self_judging_detected():
    """GLM judge on GLM generator is flagged (B6 launch-prep fix)."""
    warnings = detect_family_overlap("glm-4.7", ["glm-4.6v", "gpt-4o"])
    assert len(warnings) == 1
    assert warnings[0]["family"] == "glm"
    assert warnings[0]["model"] == "glm-4.6v"


def test_kimi_self_judging_detected():
    """Kimi judge on Kimi generator is flagged (B6 launch-prep fix)."""
    warnings = detect_family_overlap("kimi-k2.5", ["kimi-k2.5", "claude-3.5-sonnet"])
    assert len(warnings) == 1
    assert warnings[0]["family"] == "kimi"


def test_glm_and_kimi_cross_family_no_overlap():
    """GLM and Kimi are distinct families."""
    warnings = detect_family_overlap("glm-4.7", ["kimi-k2.5"])
    assert len(warnings) == 0
