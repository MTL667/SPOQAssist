# Build on DGX (requires stock tag of upstream image):
#   docker tag vllm/vllm-openai:latest vllm/vllm-openai:stock   # once
#   docker build -t vllm/vllm-openai:latest infra/dgx/vllm-reranker
# Then: docker stop vllm-reranker  # systemd respawns with wrapper
FROM vllm/vllm-openai:stock
COPY qwen3_reranker.jinja /opt/spoqsense/templates/qwen3_reranker.jinja
COPY entrypoint.sh /opt/spoqsense/entrypoint.sh
USER root
RUN chmod +x /opt/spoqsense/entrypoint.sh
ENTRYPOINT ["/opt/spoqsense/entrypoint.sh"]
