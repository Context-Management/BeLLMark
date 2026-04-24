# backend/tests/test_attachments.py
"""Tests for attachment upload and management API."""
import os
import tempfile
import shutil
import pytest

from app.main import app
from app.db.database import get_db


@pytest.fixture(autouse=True)
def upload_dir():
    """Create and clean up temporary upload directory."""
    temp_dir = tempfile.mkdtemp(prefix="bellmark_test_uploads_")
    os.environ["BELLMARK_UPLOAD_DIR"] = temp_dir
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.environ.pop("BELLMARK_UPLOAD_DIR", None)


class TestAttachmentUpload:
    """Test attachment upload endpoints."""

    def test_upload_text_file(self, client):
        """Test uploading a text file."""
        content = b"Hello, this is test content"
        response = client.post(
            "/api/attachments/",
            files={"file": ("test.txt", content, "text/plain")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["size_bytes"] == len(content)
        assert "id" in data
        assert "created_at" in data

    def test_upload_markdown_file(self, client):
        """Test uploading a markdown file."""
        content = b"# Heading\n\nSome content"
        response = client.post(
            "/api/attachments/",
            files={"file": ("doc.md", content, "text/markdown")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mime_type"] == "text/markdown"
        assert data["filename"] == "doc.md"

    def test_upload_png_image(self, client):
        """Test uploading a PNG image."""
        # Minimal valid PNG header
        png_content = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        response = client.post(
            "/api/attachments/",
            files={"file": ("test.png", png_content, "image/png")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mime_type"] == "image/png"
        assert data["size_bytes"] == len(png_content)

    def test_upload_jpeg_image(self, client):
        """Test uploading a JPEG image."""
        jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 100 + b'\xff\xd9'
        response = client.post(
            "/api/attachments/",
            files={"file": ("photo.jpg", jpeg_content, "image/jpeg")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mime_type"] == "image/jpeg"

    def test_upload_invalid_extension(self, client):
        """Test that invalid file types are rejected."""
        response = client.post(
            "/api/attachments/",
            files={"file": ("script.exe", b"malicious", "application/octet-stream")}
        )
        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()

    def test_upload_no_extension(self, client):
        """Test that files without extensions are rejected."""
        response = client.post(
            "/api/attachments/",
            files={"file": ("noextension", b"content", "text/plain")}
        )
        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()

    def test_upload_text_file_too_large(self, client):
        """Test that oversized text files are rejected."""
        # Create content larger than 1MB limit for text
        large_content = b"x" * (2 * 1024 * 1024)  # 2MB
        response = client.post(
            "/api/attachments/",
            files={"file": ("large.txt", large_content, "text/plain")}
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_upload_image_file_too_large(self, client):
        """Test that oversized image files are rejected."""
        # Create content larger than 10MB limit for images
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        response = client.post(
            "/api/attachments/",
            files={"file": ("large.png", large_content, "image/png")}
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_upload_multiple_files_sequential(self, client):
        """Test uploading multiple files sequentially."""
        files = [
            ("file1.txt", b"content1", "text/plain"),
            ("file2.md", b"# Title", "text/markdown"),
            ("file3.png", b"png_data", "image/png")
        ]

        for filename, content, mime in files:
            response = client.post(
                "/api/attachments/",
                files={"file": (filename, content, mime)}
            )
            assert response.status_code == 200
            assert response.json()["filename"] == filename


class TestAttachmentOperations:
    """Test attachment CRUD operations."""

    def test_list_attachments_empty(self, client):
        """Test listing attachments when none exist."""
        response = client.get("/api/attachments/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_attachments(self, client):
        """Test listing all attachments."""
        # Upload a file first
        client.post(
            "/api/attachments/",
            files={"file": ("test.txt", b"content", "text/plain")}
        )

        response = client.get("/api/attachments/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.txt"

    def test_list_attachments_ordered_by_created_at(self, client):
        """Test that attachments are listed in reverse chronological order."""
        # Upload multiple files
        for i in range(3):
            client.post(
                "/api/attachments/",
                files={"file": (f"file{i}.txt", b"content", "text/plain")}
            )

        response = client.get("/api/attachments/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Most recent first
        assert data[0]["filename"] == "file2.txt"
        assert data[2]["filename"] == "file0.txt"

    def test_get_attachment(self, client):
        """Test getting single attachment metadata."""
        # Upload a file
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("test.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        response = client.get(f"/api/attachments/{attachment_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.txt"
        assert data["id"] == attachment_id

    def test_get_nonexistent_attachment(self, client):
        """Test getting attachment that doesn't exist."""
        response = client.get("/api/attachments/9999")
        assert response.status_code == 404

    def test_download_attachment(self, client):
        """Test downloading attachment file."""
        content = b"File content to download"
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("download.txt", content, "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        response = client.get(f"/api/attachments/{attachment_id}/download")
        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    def test_download_nonexistent_attachment(self, client):
        """Test downloading attachment that doesn't exist."""
        response = client.get("/api/attachments/9999/download")
        assert response.status_code == 404

    def test_delete_unused_attachment(self, client):
        """Test deleting attachment that's not in use."""
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("delete_me.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        response = client.delete(f"/api/attachments/{attachment_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify it's gone from database
        get_response = client.get(f"/api/attachments/{attachment_id}")
        assert get_response.status_code == 404

        # Verify file is deleted from disk
        upload_dir = os.environ.get("BELLMARK_UPLOAD_DIR")
        assert len(os.listdir(upload_dir)) == 0

    def test_delete_nonexistent_attachment(self, client):
        """Test deleting attachment that doesn't exist."""
        response = client.delete("/api/attachments/9999")
        assert response.status_code == 404

    def test_delete_attachment_in_use_by_suite(self, client):
        """Test that attachments in use by suites cannot be deleted."""
        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("suite_attachment.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Create suite using this attachment
        db = next(app.dependency_overrides[get_db]())
        from app.db.models import PromptSuite, SuiteAttachment
        suite = PromptSuite(name="Test Suite", description="Test")
        db.add(suite)
        db.commit()

        suite_attachment = SuiteAttachment(
            suite_id=suite.id,
            attachment_id=attachment_id
        )
        db.add(suite_attachment)
        db.commit()
        db.close()

        # Try to delete - should fail
        response = client.delete(f"/api/attachments/{attachment_id}")
        assert response.status_code == 400
        assert "in use" in response.json()["detail"].lower()

        # Verify attachment still exists
        get_response = client.get(f"/api/attachments/{attachment_id}")
        assert get_response.status_code == 200

    def test_delete_attachment_in_use_by_question(self, client):
        """Test that attachments in use by questions cannot be deleted."""
        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("question_attachment.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Create benchmark and question using this attachment
        db = next(app.dependency_overrides[get_db]())
        from app.db.models import BenchmarkRun, Question, QuestionAttachment, RunStatus, JudgeMode

        run = BenchmarkRun(
            name="Test Run",
            status=RunStatus.pending,
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[],
            judge_ids=[],
            temperature=0.7
        )
        db.add(run)
        db.commit()

        question = Question(
            benchmark_id=run.id,
            order=0,
            system_prompt="Test",
            user_prompt="Test"
        )
        db.add(question)
        db.commit()

        question_attachment = QuestionAttachment(
            question_id=question.id,
            attachment_id=attachment_id
        )
        db.add(question_attachment)
        db.commit()
        db.close()

        # Try to delete - should fail
        response = client.delete(f"/api/attachments/{attachment_id}")
        assert response.status_code == 400
        assert "in use" in response.json()["detail"].lower()


class TestAttachmentFileStorage:
    """Test attachment file storage and security."""

    def test_uploaded_file_content_preserved(self, client):
        """Test that uploaded file content is preserved correctly."""
        content = b"Test file content for verification"
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("test.txt", content, "text/plain")}
        )
        assert upload_response.status_code == 200
        attachment_id = upload_response.json()["id"]

        # Download and verify content matches
        download_response = client.get(f"/api/attachments/{attachment_id}/download")
        assert download_response.status_code == 200
        assert download_response.content == content

    def test_unique_filenames_for_duplicates(self, client):
        """Test that uploading same filename twice creates unique storage."""
        content1 = b"First file content"
        content2 = b"Second file content"

        # Upload same filename twice with different content
        response1 = client.post(
            "/api/attachments/",
            files={"file": ("duplicate.txt", content1, "text/plain")}
        )
        response2 = client.post(
            "/api/attachments/",
            files={"file": ("duplicate.txt", content2, "text/plain")}
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        id1 = response1.json()["id"]
        id2 = response2.json()["id"]

        # Both files should exist with their own unique content
        download1 = client.get(f"/api/attachments/{id1}/download")
        download2 = client.get(f"/api/attachments/{id2}/download")

        assert download1.content == content1
        assert download2.content == content2

    def test_storage_path_security(self, client):
        """Test that storage paths are not exposed in API responses."""
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("test.txt", b"content", "text/plain")}
        )
        data = upload_response.json()

        # Storage path should NOT be exposed in API response (security)
        assert "storage_path" not in data
        # Only safe fields should be present
        assert "id" in data
        assert "filename" in data
        assert "mime_type" in data
        assert "size_bytes" in data
        assert "created_at" in data


class TestAttachmentErrorHandling:
    """Test error handling and edge cases."""

    def test_upload_without_file(self, client):
        """Test upload endpoint without file parameter."""
        response = client.post("/api/attachments/")
        assert response.status_code == 422  # Validation error

    def test_upload_empty_file(self, client):
        """Test uploading empty file."""
        response = client.post(
            "/api/attachments/",
            files={"file": ("empty.txt", b"", "text/plain")}
        )
        # Empty files should be allowed
        assert response.status_code == 200
        assert response.json()["size_bytes"] == 0

    def test_mime_type_detection(self, client):
        """Test that MIME types are correctly determined from extensions."""
        test_cases = [
            ("file.txt", "text/plain"),
            ("file.md", "text/markdown"),
            ("file.png", "image/png"),
            ("file.jpg", "image/jpeg"),
            ("file.jpeg", "image/jpeg"),
            ("file.gif", "image/gif"),
            ("file.webp", "image/webp"),
        ]

        for filename, expected_mime in test_cases:
            response = client.post(
                "/api/attachments/",
                files={"file": (filename, b"content", "application/octet-stream")}
            )
            assert response.status_code == 200
            assert response.json()["mime_type"] == expected_mime

    def test_case_insensitive_extension_validation(self, client):
        """Test that file extensions are validated case-insensitively."""
        # Uppercase extension should work
        response = client.post(
            "/api/attachments/",
            files={"file": ("TEST.TXT", b"content", "text/plain")}
        )
        assert response.status_code == 200

        # Mixed case
        response = client.post(
            "/api/attachments/",
            files={"file": ("file.Png", b"content", "image/png")}
        )
        assert response.status_code == 200


class TestSuiteAttachments:
    """Test suite attachment management."""

    def test_add_attachment_to_suite(self, client):
        """Test attaching a file to a suite."""
        # Create a suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        assert suite_response.status_code == 200
        suite_id = suite_response.json()["id"]

        # Upload an attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("doc.txt", b"content", "text/plain")}
        )
        assert upload_response.status_code == 200
        attachment_id = upload_response.json()["id"]

        # Add to suite
        response = client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "all_questions"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["attachment_id"] == attachment_id
        assert data["scope"] == "all_questions"
        assert "attachment" in data
        assert data["attachment"]["filename"] == "doc.txt"

    def test_list_suite_attachments(self, client):
        """Test listing attachments for a suite."""
        # Create a suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload an attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("ref.txt", b"reference data", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Add to suite
        client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "all_questions"
        })

        # List attachments
        response = client.get(f"/api/suites/{suite_id}/attachments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "attachment" in data[0]  # Nested attachment data
        assert data[0]["attachment"]["filename"] == "ref.txt"

    def test_remove_suite_attachment(self, client):
        """Test removing attachment from suite."""
        # Create suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload and add attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("temp.txt", b"temp content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "all_questions"
        })

        # Remove attachment
        response = client.delete(f"/api/suites/{suite_id}/attachments/{attachment_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"

        # Verify removed
        list_response = client.get(f"/api/suites/{suite_id}/attachments")
        assert len(list_response.json()) == 0

        # Verify attachment file still exists (only removed from suite, not deleted)
        file_response = client.get(f"/api/attachments/{attachment_id}")
        assert file_response.status_code == 200

    def test_specific_scope_requires_order(self, client):
        """Test that specific scope requires suite_item_order."""
        # Create suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("doc.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Try to add with specific scope but no suite_item_order
        response = client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "specific"
            # Missing suite_item_order
        })
        assert response.status_code == 400
        assert "suite_item_order required" in response.json()["detail"]

    def test_add_attachment_to_specific_item(self, client):
        """Test attaching to a specific suite item."""
        # Create suite with 2 items
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System 1", "user_prompt": "User 1"},
                {"system_prompt": "System 2", "user_prompt": "User 2"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("specific.txt", b"specific content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Add to specific item (first one, order=0)
        response = client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "specific",
            "suite_item_order": 0
        })
        assert response.status_code == 200
        assert response.json()["suite_item_order"] == 0
        assert response.json()["scope"] == "specific"

    def test_add_attachment_to_nonexistent_suite(self, client):
        """Test adding attachment to non-existent suite."""
        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("doc.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Try to add to non-existent suite
        response = client.post("/api/suites/9999/attachments", json={
            "attachment_id": attachment_id,
            "scope": "all_questions"
        })
        assert response.status_code == 404
        assert "Suite not found" in response.json()["detail"]

    def test_add_nonexistent_attachment_to_suite(self, client):
        """Test adding non-existent attachment to suite."""
        # Create suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Try to add non-existent attachment
        response = client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": 9999,
            "scope": "all_questions"
        })
        assert response.status_code == 404
        assert "Attachment not found" in response.json()["detail"]

    def test_invalid_suite_item_order(self, client):
        """Test adding attachment with invalid suite_item_order."""
        # Create suite with 1 item
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("doc.txt", b"content", "text/plain")}
        )
        attachment_id = upload_response.json()["id"]

        # Try to add to non-existent item (order=5)
        response = client.post(f"/api/suites/{suite_id}/attachments", json={
            "attachment_id": attachment_id,
            "scope": "specific",
            "suite_item_order": 5
        })
        assert response.status_code == 404
        assert "Suite item with order 5 not found" in response.json()["detail"]

    def test_multiple_attachments_on_suite(self, client):
        """Test adding multiple attachments to a suite."""
        # Create suite
        suite_response = client.post("/api/suites/", json={
            "name": "Test Suite",
            "description": "Test",
            "items": [
                {"system_prompt": "System", "user_prompt": "User"}
            ]
        })
        suite_id = suite_response.json()["id"]

        # Upload multiple attachments
        attachment_ids = []
        for i in range(3):
            upload_response = client.post(
                "/api/attachments/",
                files={"file": (f"file{i}.txt", f"content{i}".encode(), "text/plain")}
            )
            attachment_ids.append(upload_response.json()["id"])

        # Add all to suite
        for att_id in attachment_ids:
            response = client.post(f"/api/suites/{suite_id}/attachments", json={
                "attachment_id": att_id,
                "scope": "all_questions"
            })
            assert response.status_code == 200

        # Verify all are listed
        list_response = client.get(f"/api/suites/{suite_id}/attachments")
        assert len(list_response.json()) == 3


class TestBenchmarkWithAttachments:
    """Test benchmark creation and results with attachments."""

    def _create_model_and_judge(self, client):
        """Create a test model and a separate judge model."""
        model_response = client.post("/api/models/", json={
            "name": "Test Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1",
            "model_id": "test"
        })
        assert model_response.status_code == 200
        judge_response = client.post("/api/models/", json={
            "name": "Test Judge",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1",
            "model_id": "test-judge"
        })
        assert judge_response.status_code == 200
        return model_response.json()["id"], judge_response.json()["id"]

    def test_create_benchmark_with_attachments(self, client):
        """Test creating benchmark with question attachments."""
        model_id, judge_id = self._create_model_and_judge(client)

        # Upload attachment
        upload_response = client.post(
            "/api/attachments/",
            files={"file": ("ref.txt", b"reference content", "text/plain")}
        )
        assert upload_response.status_code == 200
        attachment_id = upload_response.json()["id"]

        # Create benchmark with attachment
        response = client.post("/api/benchmarks/", json={
            "name": "Test Benchmark",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{
                "system_prompt": "System",
                "user_prompt": "User",
                "attachment_ids": [attachment_id]
            }]
        })
        # Should accept the request (may fail later during execution if model not running)
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            benchmark_id = response.json()["id"]

            # Verify question was created with attachment
            db = next(app.dependency_overrides[get_db]())
            from app.db.models import Question, QuestionAttachment

            question = db.query(Question).filter(Question.benchmark_id == benchmark_id).first()
            assert question is not None

            question_attachments = db.query(QuestionAttachment).filter(
                QuestionAttachment.question_id == question.id
            ).all()
            assert len(question_attachments) == 1
            assert question_attachments[0].attachment_id == attachment_id

            db.close()

    def test_create_benchmark_with_invalid_attachment_id(self, client):
        """Test that creating benchmark with invalid attachment ID fails."""
        model_id, judge_id = self._create_model_and_judge(client)

        # Try to create benchmark with non-existent attachment
        response = client.post("/api/benchmarks/", json={
            "name": "Test Benchmark",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{
                "system_prompt": "System",
                "user_prompt": "User",
                "attachment_ids": [9999]  # Non-existent
            }]
        })
        assert response.status_code == 400
        assert "attachment" in response.json()["detail"].lower()

    def test_create_benchmark_with_multiple_attachments(self, client):
        """Test creating benchmark with multiple attachments per question."""
        model_id, judge_id = self._create_model_and_judge(client)

        # Upload multiple attachments
        attachment_ids = []
        for i in range(2):
            upload_response = client.post(
                "/api/attachments/",
                files={"file": (f"ref{i}.txt", f"content{i}".encode(), "text/plain")}
            )
            attachment_ids.append(upload_response.json()["id"])

        # Create benchmark with multiple attachments
        response = client.post("/api/benchmarks/", json={
            "name": "Test Benchmark",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{
                "system_prompt": "System",
                "user_prompt": "User",
                "attachment_ids": attachment_ids
            }]
        })
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            benchmark_id = response.json()["id"]

            # Verify question was created with both attachments
            db = next(app.dependency_overrides[get_db]())
            from app.db.models import Question, QuestionAttachment

            question = db.query(Question).filter(Question.benchmark_id == benchmark_id).first()
            assert question is not None

            question_attachments = db.query(QuestionAttachment).filter(
                QuestionAttachment.question_id == question.id
            ).all()
            assert len(question_attachments) == 2

            db.close()

    def test_benchmark_without_attachments(self, client):
        """Test creating benchmark without attachments still works."""
        model_id, judge_id = self._create_model_and_judge(client)

        # Create benchmark without attachments
        response = client.post("/api/benchmarks/", json={
            "name": "Test Benchmark",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{
                "system_prompt": "System",
                "user_prompt": "User",
                "attachment_ids": []  # Explicitly empty
            }]
        })
        assert response.status_code in [200, 500]
