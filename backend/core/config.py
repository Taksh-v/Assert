"""
Assest — Configuration Management
Loads all settings from environment variables via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # ── App ──────────────────────────────────────────────
    app_env: str = Field(default="development", description="development | production")
    app_secret_key: str = Field(default="change-me-to-a-random-64-char-string")
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    app_version: str = Field(default="0.1.0")
    sql_echo: bool = Field(
        default=False,
        alias="SQL_ECHO",
        description="Enable verbose SQLAlchemy SQL logging when debugging database queries.",
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated list of allowed CORS origins",
    )

    # ── Database ─────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/assest_dev.db",
        description="SQLite for dev, PostgreSQL for prod",
    )
    supabase_url: Optional[str] = Field(default=None, description="Supabase project URL")
    supabase_anon_key: Optional[str] = Field(default=None, description="Supabase anon key")
    supabase_service_role_key: Optional[str] = Field(
        default=None,
        description="Supabase service role key for server-side storage and admin tasks",
    )
    supabase_storage_bucket: str = Field(default="raw-storage")

    # ── Vector Database (Qdrant) ─────────────────────────
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_collection_name: str = Field(default="assest_knowledge_dev")
    qdrant_episodes_collection_name: str = Field(default="assest_episodes_dev")
    qdrant_mode: str = Field(
        default="local",
        description="'local' for file-based (dev), 'server' for remote Qdrant, 'memory' for ephemeral",
    )
    qdrant_path: str = Field(default="./data/qdrant")
    qdrant_api_key: Optional[str] = Field(default=None, description="API key for Qdrant Cloud authentication")
    # Qdrant performance tuning
    qdrant_upsert_batch_size: int = Field(default=256, description="Preferred batch size when upserting points to Qdrant")
    qdrant_write_concurrency: int = Field(default=2, description="Number of concurrent threads to use for large upsert operations")

    # ── Redis ────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── LLM Gateway (LiteLLM) ──────────────────────────
    litellm_proxy_url: Optional[str] = Field(default="http://localhost:4000", description="Local LiteLLM proxy URL")
    company_brain_fast_model: str = Field(default="openai/company-brain-fast")
    company_brain_smart_model: str = Field(default="openai/company-brain-smart")
    openrouter_api_key: Optional[str] = Field(default=None)
    openrouter_api_base: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_site_url: Optional[str] = Field(default=None)
    openrouter_app_name: str = Field(default="Assest Brain")
    openrouter_fast_model: str = Field(default="openrouter/google/gemini-2.0-flash-lite:free")
    openrouter_smart_model: str = Field(default="openrouter/meta-llama/llama-3.1-8b-instruct:free")
    # Optional comma-separated fallback models for OpenRouter (tried in order)
    openrouter_fallback_models: str = Field(
        default="openrouter/z-ai/glm-4.5-air:free",
        description="Comma-separated OpenRouter model ids to try as fallbacks",
    )
    openrouter_retry_attempts: int = Field(default=3, description="Number of retry attempts per model")
    openrouter_retry_backoff_base: float = Field(default=0.5, description="Base backoff in seconds")
    openrouter_prompt_cache_retention: str = Field(
        default="in_memory",
        description="Prompt cache retention policy passed to supported providers",
    )
    llm_default_max_output_tokens_fast: int = Field(
        default=192,
        description="Default completion budget for fast/control-plane model calls",
    )
    llm_default_max_output_tokens_smart: int = Field(
        default=384,
        description="Default completion budget for smart generation model calls",
    )
    llm_request_timeout: float = Field(
        default=5.0,
        description="Timeout in seconds for LLM completion requests",
    )
    llm_router_max_output_tokens: int = Field(
        default=96,
        description="Token cap for intent/routing classification calls",
    )
    llm_verifier_max_output_tokens: int = Field(
        default=128,
        description="Token cap for verification and other structured control-plane calls",
    )

    # ── Langfuse Observability ──────────────────────────
    langfuse_public_key: Optional[str] = Field(default="pk-lf-public", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default="sk-lf-secret", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")

    # ── LLM — Groq ──────────────────────────────────────
    groq_api_key: Optional[str] = Field(default=None)
    groq_model: str = Field(default="groq/llama-3.3-70b-versatile")

    # ── Embeddings ───────────────────────────────────────
    load_local_models: bool = Field(default=True, alias="ASSEST_LOAD_LOCAL_MODELS")
    embedding_provider: str = Field(
        default="local",
        description="'local' for sentence-transformers, 'openai' for OpenAI API",
    )
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    openai_api_key: Optional[str] = Field(default=None)

    # ── Reranking ────────────────────────────────────────
    enable_reranking: bool = Field(default=True)
    rerank_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    rerank_top_k: int = Field(default=5)

    # ── AWS ──────────────────────────────────────────────
    aws_access_key_id: Optional[str] = Field(default=None)
    aws_secret_access_key: Optional[str] = Field(default=None)
    aws_region: str = Field(default="ap-south-1")
    aws_s3_bucket: str = Field(default="assest-raw-documents")

    # ── Notion OAuth ──────────────────────────────────────
    notion_token: Optional[str] = Field(default=None, description="Internal integration token (quick setup)")
    notion_client_id: Optional[str] = Field(default=None)
    notion_client_secret: Optional[str] = Field(default=None)
    notion_redirect_uri: str = Field(default="http://localhost:8000/api/auth/notion/callback")

    # ── Google Drive OAuth (Connector) ───────────────────
    google_client_id: Optional[str] = Field(default=None)
    google_client_secret: Optional[str] = Field(default=None)
    google_redirect_uri: str = Field(default="http://localhost:8000/api/auth/google/callback")
    google_identity_redirect_uri: str = Field(default="http://localhost:8000/api/auth/identity/google/callback")
    google_scopes: str = Field(default="https://www.googleapis.com/auth/drive.readonly")

    # ── GitHub OAuth (Identity) ──────────────────────────
    github_client_id: Optional[str] = Field(default=None)
    github_client_secret: Optional[str] = Field(default=None)
    github_redirect_uri: str = Field(default="http://localhost:8000/api/auth/identity/github/callback")

    # ── Facebook OAuth (Identity) ────────────────────────
    facebook_client_id: Optional[str] = Field(default=None)
    facebook_client_secret: Optional[str] = Field(default=None)
    facebook_redirect_uri: str = Field(default="http://localhost:8000/api/auth/identity/facebook/callback")

    # ── Slack OAuth ──────────────────────────────────────
    slack_client_id: Optional[str] = Field(default=None)
    slack_client_secret: Optional[str] = Field(default=None)
    slack_redirect_uri: str = Field(default="http://localhost:8000/api/auth/slack/callback")
    slack_bot_token: Optional[str] = Field(default=None)
    slack_app_token: Optional[str] = Field(default=None)
    slack_signing_secret: Optional[str] = Field(default=None)
    enable_slack_bot: bool = Field(
        default=False,
        alias="ENABLE_SLACK_BOT",
        description="Start the realtime Slack Socket Mode bot on backend startup.",
    )

    # ── Memgraph (Graph Database) ────────────────────────
    memgraph_url: str = Field(default="bolt://localhost:7687")
    memgraph_user: str = Field(default="memgraph")
    memgraph_password: str = Field(default="")

    # ── Frontend ─────────────────────────────────────────
    frontend_url: str = Field(default="http://localhost:3000")

    # ── Agent Orchestration ──────────────────────────────
    enable_multi_agent: bool = Field(default=True, description="Enable LangGraph-based multi-agent orchestration")
    enable_online_evaluations: bool = Field(
        default=False,
        description="Enable expensive online faithfulness/relevance scoring in the request path",
    )
    online_evaluation_sample_rate: float = Field(
        default=0.05,
        description="Sampling rate for online evaluation when enabled",
    )
    enable_hyde: bool = Field(
        default=True,
        description="Enable HyDE query expansion when retrieval confidence is weak",
    )
    hyde_min_query_words: int = Field(
        default=6,
        description="Minimum query length before HyDE expansion can trigger",
    )
    enable_graph_retrieval: bool = Field(
        default=True,
        description="Enable graph-based retrieval augmentation",
    )
    crag_skip_high_confidence_threshold: float = Field(
        default=0.82,
        description="If top retrieval confidence is above this threshold, skip CRAG verification",
    )

    # ── Worker Pool ──────────────────────────────────────
    enable_workers: bool = Field(default=True)
    worker_workspace_id: str = Field(default="default_workspace")
    worker_fetch_count: int = Field(default=3)
    worker_parser_count: int = Field(default=2)
    worker_enrichment_count: int = Field(default=2)
    worker_embedding_count: int = Field(default=2)
    worker_max_concurrent_tasks: int = Field(default=5)
    worker_batch_size: int = Field(default=10)

    # ── Auto Ingest Scheduler ───────────────────────────
    enable_auto_ingest: bool = Field(
        default=True,
        description="Enable periodic automatic ingestion for active connectors",
    )
    auto_ingest_interval_minutes: int = Field(
        default=60,
        description="Interval in minutes between auto ingestion passes",
    )

    # ── Metrics / Prometheus ───────────────────────────
    enable_prometheus: bool = Field(
        default=False,
        description="Enable Prometheus metrics exposition and collection",
    )
    prometheus_port: int = Field(
        default=8001,
        description="Port to expose Prometheus metrics on when enabled",
    )

    # ── Startup Validation Flags ───────────────────────
    strict_model_validation: bool = Field(
        default=False,
        description="If true, fail startup when LLM model validation warnings are present",
    )
    perform_llm_ping: bool = Field(
        default=False,
        description="If true, perform a live ping test against the primary model during /api/llm/health checks.",
    )
    active_ping_on_startup: bool = Field(
        default=False,
        description="If true, perform a live ping test against the primary model during startup validation.",
    )

    # ── Pilot Flags ─────────────────────────────────────
    pilot_connectors: str = Field(
        default="",
        description="Comma-separated list of connector ids or connector types to pilot the new sync runner. Empty means run everywhere.",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and (self.supabase_service_role_key or self.supabase_anon_key))

    @property
    def pilot_connectors_list(self) -> list[str]:
        if not self.pilot_connectors:
            return []
        return [s.strip().lower() for s in self.pilot_connectors.split(",") if s.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance.
    Call this function anywhere in the app to get the current config.
    """
    return Settings()
