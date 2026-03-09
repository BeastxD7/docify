from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Q&A synthesis
    llm_provider: str = "anthropic"       # anthropic | ollama
    llm_model: str = "claude-haiku-4-5-20251001"

    # Graph entity/relation extraction (needs high instruction-following)
    extraction_llm_provider: str = "anthropic"
    extraction_llm_model: str = "claude-sonnet-4-6"

    # Community summarization (bulk, cost-sensitive)
    summary_llm_provider: str = "anthropic"
    summary_llm_model: str = "claude-haiku-4-5-20251001"

    # Embeddings
    embedding_provider: str = "openai"    # openai | ollama
    embedding_model: str = "text-embedding-3-large"
    ollama_base_url: str = "http://localhost:11434"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "docify"
    postgres_user: str = "docify"
    postgres_password: str = "docify"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "docify_chunks"

    # Neo4j (Phase 2)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "docify_neo4j"

    # Files
    upload_dir: str = "/data/uploads"
    max_file_size_mb: int = 500

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64


settings = Settings()
