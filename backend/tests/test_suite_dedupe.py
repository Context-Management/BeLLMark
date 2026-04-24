"""Tests for dedupe heuristics used by suite generation."""

from app.core.suite_coverage import (
    cluster_duplicate_pairs,
    find_candidate_duplicate_pairs,
    normalized_prompt_fingerprint,
    trigram_jaccard,
)


def test_normalized_prompt_fingerprint_matches_equivalent_text():
    left = normalized_prompt_fingerprint("Explain SSE.", "Use bullet points.")
    right = normalized_prompt_fingerprint(" explain sse ", "Use bullet points")
    assert left == right


def test_trigram_jaccard_is_high_for_near_identical_prompts():
    score = trigram_jaccard("build a websocket streaming service", "build websocket streaming service")
    assert score > 0.5


def test_find_candidate_duplicate_pairs_prefers_exact_and_near_matches():
    questions = [
        {"system_prompt": "Sys", "user_prompt": "Explain SSE streaming."},
        {"system_prompt": "Sys", "user_prompt": "Explain SSE streaming."},
        {"system_prompt": "Sys", "user_prompt": "Design a websocket relay."},
    ]

    pairs = find_candidate_duplicate_pairs(questions)

    assert (0, 1) in pairs
    assert all(pair != (0, 2) for pair in pairs)


def test_cluster_duplicate_pairs_merges_connected_components():
    clusters = cluster_duplicate_pairs([(0, 1), (1, 2), (4, 5)])
    assert sorted(sorted(cluster) for cluster in clusters) == [[0, 1, 2], [4, 5]]
