"""Tests for suite-criteria bundles and expected answers."""
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import PromptSuite, PromptSuiteItem, Question


class TestSuiteModels:
    def test_suite_has_default_criteria_field(self):
        suite = PromptSuite(name="Test", default_criteria=[{"name": "Accuracy", "description": "Test", "weight": 1.0}])
        assert suite.default_criteria == [{"name": "Accuracy", "description": "Test", "weight": 1.0}]

    def test_suite_default_criteria_is_nullable(self):
        suite = PromptSuite(name="Test")
        assert suite.default_criteria is None

    def test_suite_item_has_expected_answer_field(self):
        item = PromptSuiteItem(suite_id=1, order=0, system_prompt="sys", user_prompt="usr", expected_answer="expected")
        assert item.expected_answer == "expected"

    def test_suite_item_expected_answer_is_nullable(self):
        item = PromptSuiteItem(suite_id=1, order=0, system_prompt="sys", user_prompt="usr")
        assert item.expected_answer is None

    def test_question_has_expected_answer_field(self):
        q = Question(benchmark_id=1, order=0, system_prompt="sys", user_prompt="usr", expected_answer="ans")
        assert q.expected_answer == "ans"

    def test_suite_item_supports_pipeline_metadata(self):
        item = PromptSuiteItem(
            suite_id=1,
            order=0,
            system_prompt="sys",
            user_prompt="usr",
            expected_answer="gold",
            category="coding",
            difficulty="hard",
            criteria=[
                {"name": "Trade-offs", "description": "Compares multiple designs", "weight": 1.0}
            ],
        )
        assert item.category == "coding"
        assert item.difficulty == "hard"
        assert item.criteria[0]["name"] == "Trade-offs"


class TestSuiteCRUDWithCriteria:
    """Test suite CRUD operations with default_criteria and expected_answer."""

    def test_create_suite_with_criteria(self, client):
        data = {
            "name": "Test Suite",
            "description": "With criteria",
            "items": [{"system_prompt": "sys", "user_prompt": "question 1"}],
            "default_criteria": [
                {"name": "Accuracy", "description": "Factual correctness", "weight": 1.0}
            ]
        }
        resp = client.post("/api/suites/", json=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["default_criteria"] == data["default_criteria"]

    def test_create_suite_without_criteria(self, client):
        data = {
            "name": "No Criteria Suite",
            "items": [{"system_prompt": "", "user_prompt": "question 1"}]
        }
        resp = client.post("/api/suites/", json=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["default_criteria"] is None

    def test_create_suite_with_expected_answer(self, client):
        data = {
            "name": "Suite With Answers",
            "items": [
                {"system_prompt": "sys", "user_prompt": "q1", "expected_answer": "answer 1"},
                {"system_prompt": "sys", "user_prompt": "q2"}
            ]
        }
        resp = client.post("/api/suites/", json=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"][0]["expected_answer"] == "answer 1"
        assert body["items"][1]["expected_answer"] is None

    def test_get_suite_returns_criteria(self, client):
        criteria = [{"name": "Clarity", "description": "Clear writing", "weight": 2.0}]
        create_resp = client.post("/api/suites/", json={
            "name": "Get Test",
            "items": [{"system_prompt": "", "user_prompt": "q1"}],
            "default_criteria": criteria
        })
        suite_id = create_resp.json()["id"]
        resp = client.get(f"/api/suites/{suite_id}")
        assert resp.json()["default_criteria"] == criteria

    def test_update_suite_criteria(self, client):
        create_resp = client.post("/api/suites/", json={
            "name": "Update Test",
            "items": [{"system_prompt": "", "user_prompt": "q1"}]
        })
        suite_id = create_resp.json()["id"]
        new_criteria = [{"name": "Speed", "description": "Response time", "weight": 1.5}]
        resp = client.put(f"/api/suites/{suite_id}", json={
            "name": "Updated",
            "items": [{"system_prompt": "", "user_prompt": "q1"}],
            "default_criteria": new_criteria
        })
        assert resp.status_code == 200
        assert resp.json()["default_criteria"] == new_criteria

    def test_update_suite_preserves_question_metadata(self, client):
        create_resp = client.post("/api/suites/", json={
            "name": "Update Meta",
            "items": [
                {
                    "system_prompt": "sys",
                    "user_prompt": "q1",
                    "expected_answer": "a1",
                    "category": "coding",
                    "difficulty": "hard",
                    "criteria": [
                        {"name": "Algorithm comparison", "description": "Compare options", "weight": 1.0}
                    ],
                }
            ],
        })
        suite_id = create_resp.json()["id"]

        update_resp = client.put(f"/api/suites/{suite_id}", json={
            "name": "Update Meta",
            "description": "",
            "items": [
                {
                    "system_prompt": "sys updated",
                    "user_prompt": "q1 updated",
                    "expected_answer": "a1 updated",
                    "category": "coding",
                    "difficulty": "hard",
                    "criteria": [
                        {"name": "Algorithm comparison", "description": "Compare options", "weight": 1.0}
                    ],
                }
            ],
        })
        body = update_resp.json()
        assert update_resp.status_code == 200
        assert body["items"][0]["category"] == "coding"
        assert body["items"][0]["difficulty"] == "hard"
        assert body["items"][0]["criteria"][0]["name"] == "Algorithm comparison"

    def test_list_suites_includes_criteria(self, client):
        criteria = [{"name": "Test", "description": "Desc", "weight": 1.0}]
        client.post("/api/suites/", json={
            "name": "Listed",
            "items": [{"system_prompt": "", "user_prompt": "q1"}],
            "default_criteria": criteria
        })
        resp = client.get("/api/suites/")
        assert resp.status_code == 200
        suites = resp.json()
        assert len(suites) == 1
        assert suites[0]["default_criteria"] == criteria


class TestSuiteImport:
    def test_import_minimal_suite(self, client):
        payload = {
            "name": "Imported Suite",
            "questions": [
                {"user_prompt": "What is 2+2?"}
            ]
        }
        resp = client.post("/api/suites/import", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Imported Suite"
        assert len(body["items"]) == 1
        assert body["items"][0]["user_prompt"] == "What is 2+2?"
        assert body["items"][0]["system_prompt"] == ""
        assert body["default_criteria"] is None

    def test_import_full_suite(self, client):
        payload = {
            "bellmark_version": "1.0",
            "type": "suite",
            "name": "Full Suite",
            "description": "Complete import test",
            "default_criteria": [
                {"name": "Accuracy", "description": "Factual correctness", "weight": 1.0},
                {"name": "Clarity", "description": "Clear writing", "weight": 2.0}
            ],
            "questions": [
                {"system_prompt": "Be helpful.", "user_prompt": "Explain X", "expected_answer": "X is..."},
                {"user_prompt": "What is Y?"}
            ]
        }
        resp = client.post("/api/suites/import", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Full Suite"
        assert body["description"] == "Complete import test"
        assert len(body["default_criteria"]) == 2
        assert body["default_criteria"][1]["weight"] == 2.0
        assert len(body["items"]) == 2
        assert body["items"][0]["expected_answer"] == "X is..."
        assert body["items"][1]["expected_answer"] is None

    def test_import_missing_name_returns_422(self, client):
        resp = client.post("/api/suites/import", json={
            "questions": [{"user_prompt": "q1"}]
        })
        assert resp.status_code == 422

    def test_import_empty_questions_returns_422(self, client):
        resp = client.post("/api/suites/import", json={
            "name": "Empty", "questions": []
        })
        assert resp.status_code == 422

    def test_import_missing_user_prompt_returns_422(self, client):
        resp = client.post("/api/suites/import", json={
            "name": "Bad", "questions": [{"system_prompt": "sys"}]
        })
        assert resp.status_code == 422

    def test_import_criteria_weight_defaults_to_1(self, client):
        payload = {
            "name": "Default Weight",
            "default_criteria": [{"name": "Test", "description": "Desc"}],
            "questions": [{"user_prompt": "q1"}]
        }
        resp = client.post("/api/suites/import", json=payload)
        assert resp.status_code == 200
        assert resp.json()["default_criteria"][0]["weight"] == 1.0

    def test_import_full_suite_preserves_question_metadata(self, client):
        payload = {
            "name": "Imported Suite",
            "questions": [
                {
                    "system_prompt": "You are an architect.",
                    "user_prompt": "Design a cache invalidation strategy.",
                    "expected_answer": "Use versioned keys...",
                    "category": "planning",
                    "difficulty": "medium",
                    "criteria": [
                        {"name": "Constraints", "description": "Handles cache stampede", "weight": 1.0}
                    ],
                }
            ],
        }
        resp = client.post("/api/suites/import", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"][0]["category"] == "planning"
        assert body["items"][0]["difficulty"] == "medium"
        assert body["items"][0]["criteria"][0]["name"] == "Constraints"


class TestSuiteExport:
    def test_export_suite_json_format(self, client):
        client.post("/api/suites/", json={
            "name": "Export Test",
            "description": "For export",
            "items": [
                {"system_prompt": "sys", "user_prompt": "q1", "expected_answer": "a1"},
                {"system_prompt": "", "user_prompt": "q2"}
            ],
            "default_criteria": [{"name": "Accuracy", "description": "Test", "weight": 1.5}]
        })
        suites = client.get("/api/suites/").json()
        suite_id = suites[0]["id"]

        resp = client.get(f"/api/suites/{suite_id}/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

        body = resp.json()
        assert body["bellmark_version"] == "1.0"
        assert body["type"] == "suite"
        assert body["name"] == "Export Test"
        assert body["description"] == "For export"
        assert len(body["default_criteria"]) == 1
        assert body["default_criteria"][0]["weight"] == 1.5
        assert len(body["questions"]) == 2
        assert body["questions"][0]["expected_answer"] == "a1"
        assert body["questions"][1]["expected_answer"] is None

    def test_export_suite_not_found(self, client):
        resp = client.get("/api/suites/9999/export")
        assert resp.status_code == 404

    def test_export_suite_includes_question_metadata(self, client):
        create_resp = client.post("/api/suites/", json={
            "name": "Export Meta",
            "items": [
                {
                    "system_prompt": "sys",
                    "user_prompt": "q1",
                    "expected_answer": "a1",
                    "category": "reasoning",
                    "difficulty": "easy",
                    "criteria": [
                        {"name": "Accuracy", "description": "Correct answer", "weight": 1.0}
                    ],
                }
            ],
        })
        suite_id = create_resp.json()["id"]
        exported = client.get(f"/api/suites/{suite_id}/export").json()
        assert exported["questions"][0]["category"] == "reasoning"
        assert exported["questions"][0]["difficulty"] == "easy"
        assert exported["questions"][0]["criteria"][0]["name"] == "Accuracy"

    def test_export_import_roundtrip(self, client):
        client.post("/api/suites/", json={
            "name": "Roundtrip",
            "description": "Test roundtrip",
            "items": [
                {"system_prompt": "sys", "user_prompt": "q1", "expected_answer": "a1"}
            ],
            "default_criteria": [{"name": "X", "description": "Y", "weight": 2.0}]
        })
        suite_id = client.get("/api/suites/").json()[0]["id"]
        exported = client.get(f"/api/suites/{suite_id}/export").json()

        resp = client.post("/api/suites/import", json=exported)
        assert resp.status_code == 200
        imported = resp.json()
        assert imported["name"] == "Roundtrip"
        assert imported["default_criteria"] == exported["default_criteria"]
        assert len(imported["items"]) == 1
        assert imported["items"][0]["user_prompt"] == "q1"
        assert imported["items"][0]["expected_answer"] == "a1"


class TestBenchmarkWithExpectedAnswer:
    def _create_model(self, client):
        resp = client.post("/api/models/", json={
            "name": "Test Model", "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/model"
        })
        return resp.json()["id"]

    def test_benchmark_creation_stores_expected_answer(self, client):
        model_id = self._create_model(client)
        judge_id = self._create_model(client)
        resp = client.post("/api/benchmarks/", json={
            "name": "Test Run",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Accuracy", "description": "Test", "weight": 1.0}],
            "questions": [
                {"system_prompt": "sys", "user_prompt": "q1", "expected_answer": "answer 1"},
                {"system_prompt": "sys", "user_prompt": "q2"}
            ],
            "temperature": 0.7,
            "temperature_mode": "normalized"
        })
        assert resp.status_code == 200
        run_id = resp.json()["id"]
        detail = client.get(f"/api/benchmarks/{run_id}").json()
        questions = detail["questions"]
        assert questions[0]["expected_answer"] == "answer 1"
        assert questions[1]["expected_answer"] is None


class TestImportFromUrl:
    """Tests for POST /api/suites/import-url — fetch a suite JSON from an
    allowlisted URL and reuse the existing import logic.

    This endpoint enables lightweight benchmark sharing via GitHub Gist,
    raw GitHub files, or HuggingFace dataset files, without requiring
    accounts or a community hub.
    """

    def _mock_httpx_get(self, response_payload, status_code=200):
        """Build a patch context manager that returns response_payload as JSON."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.content = (
            response_payload
            if isinstance(response_payload, (bytes, bytearray))
            else __import__("json").dumps(response_payload).encode()
        )
        mock_response.json.return_value = response_payload
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    def test_rejects_non_https_url(self, client):
        """HTTP (not HTTPS) URLs should be rejected without fetching."""
        resp = client.post(
            "/api/suites/import-url",
            json={"url": "http://raw.githubusercontent.com/foo/bar/main/suite.json"},
        )
        assert resp.status_code == 400
        assert "https" in resp.json()["detail"].lower()

    def test_rejects_disallowed_host(self, client):
        """A URL from a non-allowlisted host should be rejected."""
        resp = client.post(
            "/api/suites/import-url",
            json={"url": "https://evil.example.com/suite.json"},
        )
        assert resp.status_code == 400
        assert "host" in resp.json()["detail"].lower()

    def test_rejects_malformed_url(self, client):
        """An obviously malformed URL string should be rejected."""
        resp = client.post(
            "/api/suites/import-url",
            json={"url": "not-a-real-url"},
        )
        assert resp.status_code == 400

    def test_imports_from_github_raw_url(self, client):
        """A valid GitHub raw URL should fetch and import the suite."""
        suite_payload = {
            "bellmark_version": "1.0",
            "type": "suite",
            "name": "Imported From URL",
            "description": "Test suite imported via URL",
            "questions": [
                {
                    "system_prompt": "You are a tester.",
                    "user_prompt": "What is 2+2?",
                    "expected_answer": "4",
                    "category": "math",
                    "difficulty": "easy",
                }
            ],
        }

        mock_client = self._mock_httpx_get(suite_payload)
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/suites/import-url",
                json={
                    "url": "https://raw.githubusercontent.com/Context-Management/bellmark-benchmarks/main/test.json"
                },
            )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["name"] == "Imported From URL"
        assert len(body["items"]) == 1
        assert body["items"][0]["user_prompt"] == "What is 2+2?"
        assert body["items"][0]["expected_answer"] == "4"
        assert body["items"][0]["category"] == "math"

    def test_rejects_invalid_suite_schema_from_url(self, client):
        """If the fetched JSON doesn't match the suite schema, return 400."""
        bad_payload = {"name": "no questions field"}  # missing required `questions`

        mock_client = self._mock_httpx_get(bad_payload)
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/suites/import-url",
                json={
                    "url": "https://raw.githubusercontent.com/foo/bar/main/bad.json"
                },
            )

        assert resp.status_code == 400
        assert "schema" in resp.json()["detail"].lower() or "questions" in resp.json()["detail"].lower()
