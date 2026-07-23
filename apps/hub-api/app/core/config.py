from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EntraEntityConfig(BaseModel):
    tenant_id: str
    audience: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    spoq_env: str = "dev"
    spoq_log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://spoq:spoq_dev_change_me@localhost:5432/spoqassist"
    ollama_base_url: str = "http://host.docker.internal:11434"
    # stub | ollama | vllm
    inference_mode: str = Field(default="stub", validation_alias="INFERENCE_MODE")
    ollama_embed_model: str = Field(
        default="qwen3-embedding:0.6b", validation_alias="OLLAMA_EMBED_MODEL"
    )
    ollama_rerank_model: str = Field(
        default="qwen3-reranker:0.6b", validation_alias="OLLAMA_RERANK_MODEL"
    )
    ollama_instruct_model: str = Field(
        default="qwen3:14b", validation_alias="OLLAMA_INSTRUCT_MODEL"
    )

    # vLLM (OpenAI-compatible) — separate services per model role
    vllm_classify_url: str = Field(
        default="http://localhost:8001/v1", validation_alias="VLLM_CLASSIFY_URL"
    )
    vllm_draft_url: str = Field(
        default="http://localhost:8002/v1", validation_alias="VLLM_DRAFT_URL"
    )
    vllm_embed_url: str = Field(
        default="http://localhost:8003/v1", validation_alias="VLLM_EMBED_URL"
    )
    vllm_classify_model: str = Field(
        default="Qwen/Qwen3.6-27B", validation_alias="VLLM_CLASSIFY_MODEL"
    )
    vllm_draft_model: str = Field(
        default="Qwen/Qwen3-72B", validation_alias="VLLM_DRAFT_MODEL"
    )
    vllm_embed_model: str = Field(
        default="Qwen/Qwen3-Embedding-8B", validation_alias="VLLM_EMBED_MODEL"
    )
    vllm_vision_url: str = Field(
        default="http://localhost:8004/v1", validation_alias="VLLM_VISION_URL"
    )
    vllm_vision_model: str = Field(
        default="Qwen/Qwen2.5-VL-7B", validation_alias="VLLM_VISION_MODEL"
    )
    vllm_reranker_model: str = Field(
        default="Qwen/Qwen3-Reranker-4B", validation_alias="VLLM_RERANKER_MODEL"
    )
    vllm_reranker_url: str = Field(
        default="http://localhost:8004/v1", validation_alias="VLLM_RERANKER_URL"
    )
    vllm_draft_timeout: float = Field(
        default=12.0, validation_alias="VLLM_DRAFT_TIMEOUT"
    )
    vllm_classify_timeout: float = Field(
        default=8.0, validation_alias="VLLM_CLASSIFY_TIMEOUT"
    )

    # Multi-entity Entra: JSON list OR comma-separated tenant IDs + shared audience.
    entra_entities_json: str = Field(default="", validation_alias="ENTRA_ENTITIES")
    entra_tenant_ids: str = Field(default="", validation_alias="ENTRA_TENANT_IDS")
    entra_api_audience: str = Field(default="", validation_alias="ENTRA_API_AUDIENCE")

    # Graph OBO (hub-only secrets)
    entra_client_id: str = Field(default="", validation_alias="ENTRA_CLIENT_ID")
    entra_client_secret: str = Field(default="", validation_alias="ENTRA_CLIENT_SECRET")
    graph_scopes: str = Field(
        default=(
            "https://graph.microsoft.com/Mail.Read,"
            "https://graph.microsoft.com/Mail.Read.Shared,"
            "https://graph.microsoft.com/Mail.Send"
        ),
        validation_alias="GRAPH_SCOPES",
    )
    # stub | obo
    graph_mode: str = Field(default="stub", validation_alias="GRAPH_MODE")

    # Comma-separated principal oids allowed to manage non-content ops config (FR36)
    ops_principal_oids: str = Field(default="", validation_alias="OPS_PRINCIPAL_OIDS")

    @field_validator(
        "entra_entities_json",
        "entra_tenant_ids",
        "entra_api_audience",
        "entra_client_id",
        "entra_client_secret",
        "graph_scopes",
        "graph_mode",
        "ops_principal_oids",
        "inference_mode",
        "ollama_embed_model",
        "ollama_rerank_model",
        "ollama_instruct_model",
        "vllm_classify_url",
        "vllm_draft_url",
        "vllm_embed_url",
        "vllm_reranker_url",
        "vllm_classify_model",
        "vllm_draft_model",
        "vllm_embed_model",
        "vllm_reranker_model",
        mode="before",
    )
    @classmethod
    def _empty_str(cls, value: object) -> object:
        return "" if value is None else value

    @property
    def entra_entities(self) -> list[EntraEntityConfig]:
        raw = (self.entra_entities_json or "").strip()
        if raw:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("ENTRA_ENTITIES must be a JSON array")
            return [EntraEntityConfig.model_validate(item) for item in data]

        tenants = [t.strip() for t in (self.entra_tenant_ids or "").split(",") if t.strip()]
        audience = (self.entra_api_audience or "").strip()
        if not tenants or not audience:
            return []
        return [EntraEntityConfig(tenant_id=tid, audience=audience) for tid in tenants]

    @property
    def ops_oids(self) -> set[str]:
        return {o.strip() for o in (self.ops_principal_oids or "").split(",") if o.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
