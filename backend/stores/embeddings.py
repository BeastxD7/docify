from config import settings


def get_embedder():
    """
    Returns a LlamaIndex embedding model based on EMBEDDING_PROVIDER env var.

    openai  → text-embedding-3-large (or whatever EMBEDDING_MODEL is set to)
    ollama  → nomic-embed-text (or whatever EMBEDDING_MODEL is set to, via local Ollama)
    """
    if settings.embedding_provider == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )

    from llama_index.embeddings.ollama import OllamaEmbedding

    return OllamaEmbedding(
        model_name=settings.embedding_model,
        base_url=settings.ollama_base_url,
    )
