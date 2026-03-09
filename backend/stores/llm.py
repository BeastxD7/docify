from config import settings


def get_llm(task: str = "qa"):
    """
    Returns a LlamaIndex LLM for the given task.

    task:
      "qa"         → Q&A synthesis       (LLM_PROVIDER / LLM_MODEL)
      "extraction" → entity extraction   (EXTRACTION_LLM_PROVIDER / EXTRACTION_LLM_MODEL)
      "summary"    → community summaries (SUMMARY_LLM_PROVIDER / SUMMARY_LLM_MODEL)

    Per-task provider: anthropic | ollama
    """
    if task == "extraction":
        provider = settings.extraction_llm_provider
        model = settings.extraction_llm_model
    elif task == "summary":
        provider = settings.summary_llm_provider
        model = settings.summary_llm_model
    else:
        provider = settings.llm_provider
        model = settings.llm_model

    if provider == "ollama":
        from llama_index.llms.ollama import Ollama

        return Ollama(
            model=model,
            base_url=settings.ollama_base_url,
            request_timeout=120.0,
        )

    if provider == "groq":
        from llama_index.llms.groq import Groq

        return Groq(
            model=model,
            api_key=settings.groq_api_key,
        )

    if provider == "openrouter":
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=model,
            api_key=settings.openrouter_api_key,
            api_base=settings.openrouter_base_url,
            is_chat_model=True,
        )

    from llama_index.llms.anthropic import Anthropic

    return Anthropic(
        model=model,
        api_key=settings.anthropic_api_key,
    )
