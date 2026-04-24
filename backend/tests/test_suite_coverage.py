from app.core.suite_coverage import count_required_leaves, normalize_coverage_spec, parse_coverage_outline


def test_parse_coverage_outline_builds_groups_and_leaf_ids():
    outline = """
    A. LLM Integration & Orchestration
    - Multi-provider API abstraction
    - Streaming responses

    B. Full-Stack Web Development
    - FastAPI backends
    """

    spec = parse_coverage_outline(outline)

    assert spec["version"] == "1"
    assert len(spec["groups"]) == 2
    assert spec["groups"][0]["id"] == "a"
    assert spec["groups"][0]["leaves"][0]["id"] == "a.multi-provider-api-abstraction"


def test_normalize_coverage_spec_rejects_empty_groups():
    data = {
        "version": "1",
        "groups": [{"id": "a", "label": "A", "leaves": []}],
    }

    try:
        normalize_coverage_spec(data)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "leaves" in str(exc).lower()


def test_count_required_leaves_sums_all_leaves():
    spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A",
                "leaves": [
                    {"id": "a.one", "label": "One"},
                    {"id": "a.two", "label": "Two"},
                ],
            },
            {
                "id": "b",
                "label": "B",
                "leaves": [
                    {"id": "b.one", "label": "Three"},
                ],
            },
        ],
    }

    assert count_required_leaves(spec) == 3
