from __future__ import annotations

from app.services.retrieve import _cosine_top, _rerank


def test_rerank_falls_back_to_cosine_without_vllm(monkeypatch):
    from app.core import config as config_mod

    class _S:
        inference_mode = "stub"
        vllm_embed_url = "http://localhost:8003/v1"
        vllm_reranker_url = "http://localhost:8004/v1"
        vllm_reranker_model = "Qwen/Qwen3-Reranker-4B"

    monkeypatch.setattr(config_mod, "get_settings", lambda: _S())
    import app.services.retrieve as retrieve_mod

    retrieve_mod._reranker_disabled = False
    out = _rerank("query", [(0.9, "alpha"), (0.2, "beta")], 2)
    assert out == _cosine_top([(0.9, "alpha"), (0.2, "beta")], 2)


def test_suggestion_out_accepts_timings():
    from app.domain.enums import Confidence, HistoryStatus
    from app.domain.schemas import SuggestionOut

    out = SuggestionOut(
        suggestion_id="s1",
        mailbox_profile_id="m1",
        message_id="msg",
        category="fyi",
        priority="low",
        confidence=Confidence.HIGH,
        history_status=HistoryStatus.SUFFICIENT,
        timings={"graph_ms": 10, "retrieve_ms": 20, "classify_ms": 30, "draft_ms": 40, "total_ms": 100},
    )
    assert out.timings["total_ms"] == 100
