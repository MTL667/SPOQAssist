#!/bin/bash
# Wrapper for vllm/vllm-openai:latest used by SpoqSense systemd units.
# When the served model is a Qwen3 Reranker, force pooling + /v1/rerank.
# Otherwise pass through to stock `vllm serve`.
set -euo pipefail

joined=" $* "
if [[ "$joined" == *"Reranker"* ]] || [[ "$joined" == *"reranker"* ]]; then
  exec vllm serve /model \
    --served-model-name Qwen/Qwen3-Reranker-4B \
    --runner pooling \
    --hf_overrides '{"architectures":["Qwen3ForSequenceClassification"],"classifier_from_token":["no","yes"],"is_original_qwen3_reranker":true}' \
    --chat-template /opt/spoqsense/templates/qwen3_reranker.jinja \
    --port 8000 \
    --gpu-memory-utilization 0.12 \
    --max-model-len 4096
fi

exec vllm serve "$@"
