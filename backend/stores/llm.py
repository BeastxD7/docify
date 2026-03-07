from config import settings


def get_llm():
    """
    Returns a LlamaIndex LLM based on LLM_PROVIDER env var.

    anthropic → Claude (claude-sonnet-4-6 by default, needs ANTHROPIC_API_KEY)
    ollama    → local model via Ollama (llama3.1:8b or whatever LLM_MODEL is set to)
    """
    if settings.llm_provider == "ollama":
        from llama_index.llms.ollama import Ollama

        return Ollama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            request_timeout=120.0,  # local models can be slow on first token
        )

    from llama_index.llms.anthropic import Anthropic

    return Anthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
    )
