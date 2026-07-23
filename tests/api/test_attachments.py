"""Tests for attachment text extraction service."""

from __future__ import annotations

import pytest

from app.services.attachments import (
    AttachmentContent,
    MAX_EXTRACT_CHARS,
    extract_text,
    summarize_attachment,
)


class TestExtractText:
    def test_plaintext_file(self):
        content = extract_text("readme.txt", b"Hello, this is a test file.")
        assert content is not None
        assert content.text == "Hello, this is a test file."
        assert content.extraction_method == "text"
        assert content.mime_type == "text/plain"

    def test_csv_file(self):
        csv_data = b"name,email\nKevin,kevin@example.com\nJean,jean@example.com"
        content = extract_text("contacts.csv", csv_data)
        assert content is not None
        assert "Kevin" in content.text
        assert content.extraction_method == "text"

    def test_unsupported_extension_returns_none(self):
        content = extract_text("archive.zip", b"\x00\x01\x02")
        assert content is None

    def test_image_file_without_vllm(self, monkeypatch):
        monkeypatch.setenv("INFERENCE_MODE", "stub")
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        from app.core.config import get_settings

        get_settings.cache_clear()

        content = extract_text("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        assert content is not None
        assert content.extraction_method == "none"  # No vision in stub mode
        assert content.is_scan is True

        get_settings.cache_clear()

    def test_truncates_long_text(self):
        long_text = b"x" * (MAX_EXTRACT_CHARS + 1000)
        content = extract_text("big.txt", long_text)
        assert content is not None
        assert len(content.text) <= MAX_EXTRACT_CHARS


class TestSummarizeAttachment:
    def test_empty_text_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("INFERENCE_MODE", "stub")
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        from app.core.config import get_settings

        get_settings.cache_clear()

        result = summarize_attachment("", "empty.pdf")
        assert "could not be analyzed" in result

        get_settings.cache_clear()

    def test_stub_mode_returns_snippet(self, monkeypatch):
        monkeypatch.setenv("INFERENCE_MODE", "stub")
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        from app.core.config import get_settings

        get_settings.cache_clear()

        result = summarize_attachment("This is a contract about services.", "contract.pdf")
        assert "contract" in result.lower()

        get_settings.cache_clear()
