"""Tests for VLLMInferenceClient — OpenAI-compatible dual-model routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

import app.services.inference as inf_mod
from app.services.inference import VLLMInferenceClient, set_inference_client

# vLLM mode → 4096-dim embeddings
VLLM_DIM = 4096


@pytest.fixture(autouse=True)
def _reset_client():
    yield
    set_inference_client(None)
    inf_mod._embedding_dim = None


@pytest.fixture
def vllm_settings(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "vllm")
    monkeypatch.setenv("VLLM_CLASSIFY_URL", "http://classify:8001/v1")
    monkeypatch.setenv("VLLM_DRAFT_URL", "http://draft:8002/v1")
    monkeypatch.setenv("VLLM_EMBED_URL", "http://embed:8003/v1")
    monkeypatch.setenv("VLLM_CLASSIFY_MODEL", "Qwen/Qwen3.6-27B")
    monkeypatch.setenv("VLLM_DRAFT_MODEL", "Qwen/Qwen3-72B")
    monkeypatch.setenv("VLLM_EMBED_MODEL", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    from app.core.config import get_settings

    get_settings.cache_clear()
    inf_mod._embedding_dim = None
    yield
    get_settings.cache_clear()
    inf_mod._embedding_dim = None


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = ""
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _openai_chat_response(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _openai_embed_response(embedding: list[float]) -> dict:
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": embedding, "index": 0}],
        "model": "Qwen/Qwen3-Embedding-8B",
    }


class TestVLLMEmbed:
    def test_embed_returns_correct_dim(self, vllm_settings):
        fake_vec = [0.1] * VLLM_DIM
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(_openai_embed_response(fake_vec))

            client = VLLMInferenceClient()
            result = client.embed("test text")
            assert len(result) == VLLM_DIM
            assert result[0] == pytest.approx(0.1)

    def test_embed_truncates_oversized_vector(self, vllm_settings):
        fake_vec = [0.5] * (VLLM_DIM + 500)
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(_openai_embed_response(fake_vec))

            client = VLLMInferenceClient()
            result = client.embed("test text")
            assert len(result) == VLLM_DIM

    def test_embed_pads_undersized_vector(self, vllm_settings):
        fake_vec = [0.5] * 512
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(_openai_embed_response(fake_vec))

            client = VLLMInferenceClient()
            result = client.embed("test text")
            assert len(result) == VLLM_DIM
            assert result[511] == pytest.approx(0.5)
            assert result[512] == 0.0

    def test_embed_raises_on_http_error(self, vllm_settings):
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(
                {"error": "model loading"}, status_code=503
            )

            client = VLLMInferenceClient()
            from app.core.errors import AppError

            with pytest.raises(AppError, match="unavailable"):
                client.embed("test text")


class TestVLLMDraft:
    def test_generate_draft_uses_draft_model(self, vllm_settings):
        draft_text = "Dag Jean,\n\nIk kijk dit na.\n\nMet vriendelijke groet"
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(_openai_chat_response(draft_text))

            client = VLLMInferenceClient()
            draft, err = client._generate_draft(
                subject="Test",
                body="Beste, al nieuws?",
                sender="jean@example.com",
                mailbox_email="info@spoq.be",
                snippets=["Previous reply style example here"],
                category="action_required",
                route_email=None,
                behavior_summary="Dutch informal, concise.",
            )
            assert draft is not None
            assert err is None
            assert "Jean" in draft or "kijk" in draft
            # Verify it called the draft URL
            call_args = mock_client.post.call_args
            assert "draft:8002" in call_args[0][0]
            payload = call_args[1]["json"]
            assert payload["model"] == "Qwen/Qwen3-72B"
            assert client.draft_timeout == 30.0

    def test_generate_draft_returns_none_on_timeout(self, vllm_settings):
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ReadTimeout("timeout")

            client = VLLMInferenceClient()
            draft, err = client._generate_draft(
                subject="Test",
                body="Hello",
                sender="jean@example.com",
                mailbox_email="info@spoq.be",
                snippets=[],
                category="action_required",
                route_email=None,
            )
            assert draft is None
            assert err is not None
            assert "timed out" in err.lower()

    def test_generate_draft_rejects_parrot(self, vllm_settings):
        distinctive = "We hebben de laptop al besteld en de factuur volgt later deze week"
        draft_text = f"Dag Jean,\n\n{distinctive}.\n\nMet vriendelijke groet"
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(_openai_chat_response(draft_text))

            client = VLLMInferenceClient()
            # Body: latest message is "Nieuwe vraag" ABOVE the Original Message marker;
            # the distinctive text sits in the quoted thread context below it.
            draft, err = client._generate_draft(
                subject="Test",
                body=(
                    "Nieuwe vraag van Jean over de levering.\n\n"
                    "-----Original Message-----\n"
                    f"{distinctive}.\n\n"
                    "Met vriendelijke groet,\nKevin\n"
                ),
                sender="jean@example.com",
                mailbox_email="info@spoq.be",
                snippets=[],
                category="action_required",
                route_email=None,
            )
            assert draft is None
            assert err is not None
            assert "rejected" in err.lower() or "filtered" in err.lower()


class TestVLLMBehaviorSummary:
    def test_summarize_uses_classify_url(self, vllm_settings):
        summary_text = "Dutch, concise, professional."
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = _mock_response(
                _openai_chat_response(summary_text)
            )

            client = VLLMInferenceClient()
            result = client.summarize_mailbox_behavior(
                mailbox_email="info@spoq.be",
                kind="shared",
                chunk_count=42,
                route_lines=["facturen → boekhouding@spoq.be"],
                sample_snippets=["Dag, ik stuur dit door."],
            )
            assert "Dutch" in result or "concise" in result
            call_args = mock_client.post.call_args
            assert "classify:8001" in call_args[0][0]
            payload = call_args[1]["json"]
            assert payload["model"] == "Qwen/Qwen3.6-27B"


class TestVLLMHealth:
    def test_health_all_ok(self, vllm_settings):
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = _mock_response({"data": []})

            client = VLLMInferenceClient()
            h = client.health()
            assert h["status"] == "ok"
            assert h["mode"] == "vllm"
            assert h["services"]["classify"] == "ok"
            assert h["services"]["draft"] == "ok"
            assert h["services"]["embed"] == "ok"

    def test_health_degraded_when_one_down(self, vllm_settings):
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            def _get_side_effect(url, **kwargs):
                if "draft:8002" in url:
                    return _mock_response({}, status_code=503)
                return _mock_response({"data": []})

            mock_client.get.side_effect = _get_side_effect

            client = VLLMInferenceClient()
            h = client.health()
            assert h["status"] == "degraded"
            assert h["services"]["draft"] == "down"
            assert h["services"]["classify"] == "ok"

    def test_health_down_when_all_down(self, vllm_settings):
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("refused")

            client = VLLMInferenceClient()
            h = client.health()
            assert h["status"] == "down"


class TestEmbeddingDim:
    def test_vllm_mode_resolves_4096_dim(self, vllm_settings):
        from app.services.inference import _embedding_dim, get_embedding_dim

        # Reset cached value
        import app.services.inference as inf_mod

        inf_mod._embedding_dim = None
        dim = get_embedding_dim()
        assert dim == 4096
        inf_mod._embedding_dim = None

    def test_stub_mode_resolves_1024_dim(self, monkeypatch):
        monkeypatch.setenv("INFERENCE_MODE", "stub")
        monkeypatch.setenv("DATABASE_URL", "sqlite://")

        from app.core.config import get_settings

        get_settings.cache_clear()

        import app.services.inference as inf_mod

        inf_mod._embedding_dim = None
        dim = inf_mod.get_embedding_dim()
        assert dim == 1024
        inf_mod._embedding_dim = None
        get_settings.cache_clear()


class TestRetrieveDimMismatch:
    def test_retrieve_skips_stale_dim_chunks(self, vllm_settings):
        """Chunks with 1024-dim are skipped when running in 4096-dim mode."""
        import json

        from unittest.mock import MagicMock

        # Create a mock DB session with chunks at wrong dimension
        mock_db = MagicMock()
        chunk_1024 = MagicMock()
        chunk_1024.embedding_json = json.dumps([0.1] * 1024)
        chunk_1024.chunk_text = "old chunk"

        chunk_4096 = MagicMock()
        chunk_4096.embedding_json = json.dumps([0.2] * 4096)
        chunk_4096.chunk_text = "new chunk"

        # db.execute(select(...)).scalars() returns an iterable
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = MagicMock(return_value=iter([chunk_1024, chunk_4096]))
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Mock client that returns 4096-dim embeddings
        mock_client = MagicMock()
        mock_client.embed.return_value = [0.3] * 4096

        from app.services.retrieve import retrieve_similar

        results = retrieve_similar(
            mock_db,
            mailbox_profile_id="test-profile",
            query_text="test query",
            client=mock_client,
        )
        # Should only return the 4096-dim chunk, not the stale 1024-dim one
        assert "new chunk" in results
        assert "old chunk" not in results


class TestFactoryRouting:
    def test_factory_returns_vllm_client(self, vllm_settings):
        from app.services.inference import get_inference_client

        client = get_inference_client()
        assert isinstance(client, VLLMInferenceClient)
        set_inference_client(None)
