from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or the project .env file."""

    app_name: str = "Intelligent Hotel Platform API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/hotel_platform.db"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:8080,http://localhost:8081"
    seed_database: bool = True
    first_time_welcome_discount: float = 10.0
    jwt_secret_key: str = ""
    groq_api_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    dev_manager_email: str = "manager@example.com"
    dev_manager_password: str = ""
    ml_model_path: str = "backend/ml/artifacts/risk_model.joblib"
    ml_low_risk_threshold: float = 0.40
    ml_high_risk_threshold: float = 0.70
    # RAG reads one trusted, server-configured policy document.  Clients never
    # supply paths or collection locations.
    rag_enabled: bool = True
    rag_collection_name: str = "hotel_retention_policy"
    rag_persist_directory: str = "backend/rag_store"
    rag_embedding_model: str = "all-MiniLM-L6-v2"
    rag_top_k: int = 3
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 150
    rag_policy_document_path: str = "data/policy/Company_Retention_Policy_2026.pdf"
    # Phase 8 stores LangGraph workflow snapshots separately from business data.
    langgraph_checkpoint_path: str = "backend/data/langgraph_checkpoints.db"
    # Phase 10 is manager-only, read-only analytics.  The LLM is optional at
    # local development time; every candidate still passes AST validation.
    nl_sql_enabled: bool = True
    nl_sql_max_rows: int = 100
    nl_sql_timeout_seconds: int = 10
    nl_sql_llm_enabled: bool = False
    # Align with the existing legacy Groq configuration while keeping it
    # deployment-configurable through NL_SQL_LLM_MODEL.
    nl_sql_llm_model: str = "openai/gpt-oss-20b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Comma-separated deployment configuration, never a permissive wildcard."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
