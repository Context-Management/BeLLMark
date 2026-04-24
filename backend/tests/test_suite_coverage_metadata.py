from app.db.models import PromptSuite, PromptSuiteItem


def test_prompt_suite_supports_coverage_and_dedupe_reports():
    suite = PromptSuite(
        name="Coverage Suite",
        description="x",
        coverage_report={"covered_leaf_count": 2},
        dedupe_report={"removed_count": 1},
        generation_metadata={"coverage_mode": "strict_leaf_coverage"},
    )

    assert suite.coverage_report["covered_leaf_count"] == 2
    assert suite.dedupe_report["removed_count"] == 1
    assert suite.generation_metadata["coverage_mode"] == "strict_leaf_coverage"


def test_prompt_suite_item_supports_coverage_topic_fields():
    item = PromptSuiteItem(
        suite_id=1,
        order=0,
        system_prompt="sys",
        user_prompt="usr",
        coverage_topic_ids=["a.one"],
        coverage_topic_labels=["Topic One"],
        generation_slot_index=7,
    )

    assert item.coverage_topic_ids == ["a.one"]
    assert item.coverage_topic_labels == ["Topic One"]
    assert item.generation_slot_index == 7
