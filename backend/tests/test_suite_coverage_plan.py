from app.core.suite_coverage import build_coverage_plan, flatten_leaves


def _spec() -> dict:
    return {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A",
                "leaves": [
                    {"id": "a.one", "label": "One"},
                    {"id": "a.two", "label": "Two"},
                    {"id": "a.three", "label": "Three"},
                ],
            },
            {
                "id": "b",
                "label": "B",
                "leaves": [
                    {"id": "b.one", "label": "Four"},
                    {"id": "b.two", "label": "Five"},
                ],
            },
        ],
    }


def test_flatten_leaves_preserves_group_order():
    leaves = flatten_leaves(_spec())

    assert [leaf.id for leaf in leaves] == [
        "a.one",
        "a.two",
        "a.three",
        "b.one",
        "b.two",
    ]
    assert leaves[0].group_id == "a"
    assert leaves[-1].group_label == "B"


def test_build_coverage_plan_strict_creates_requested_slot_count_and_repeats_leaves_deterministically():
    plan = build_coverage_plan(_spec(), count=7, mode="strict_leaf_coverage", max_topics_per_question=1)

    assert plan.mode == "strict_leaf_coverage"
    assert len(plan.leaves) == 5
    assert len(plan.slots) == 7
    assert plan.slots[0].slot_index == 0
    assert plan.slots[0].required_leaf_ids == ["a.one"]
    assert plan.slots[4].required_leaf_ids == ["b.two"]
    assert plan.slots[5].required_leaf_ids == ["a.one"]
    assert plan.slots[6].required_leaf_ids == ["a.two"]


def test_build_coverage_plan_compact_groups_consecutive_leaves_within_group():
    plan = build_coverage_plan(_spec(), count=3, mode="compact_leaf_coverage", max_topics_per_question=2)

    assert plan.mode == "compact_leaf_coverage"
    assert len(plan.slots) == 3
    assert plan.slots[0].required_leaf_ids == ["a.one", "a.two"]
    assert plan.slots[1].required_leaf_ids == ["a.three"]
    assert plan.slots[2].required_leaf_ids == ["b.one", "b.two"]


def test_build_coverage_plan_rejects_unsupported_modes():
    try:
        build_coverage_plan(_spec(), count=1, mode="group_coverage", max_topics_per_question=1)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unsupported coverage mode" in str(exc).lower()
