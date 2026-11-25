"""
Provider-Agnostic LLM Service with LangChain ChatOpenAI, ChatOpenRouter & LangSmith.
Supports:
- Primary: ChatOpenAI (gpt-6-luna by default)
- Fallback 1: ChatOpenRouter (anthropic/claude-sonnet-4-5, max_tokens=2000)
- Fallback 2: Groq (OpenAI-compatible endpoint, if GROQ_API_KEY is configured)
Enforces Pydantic v2 schema validation via .with_structured_output(..., include_raw=True)
and tracks token/USD cost.
"""

from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter
from langsmith import traceable
from pydantic import BaseModel, SecretStr

from app.config import settings

T = TypeVar("T", bound=BaseModel)

# Approximate pricing per 1M tokens (USD) for cost visibility
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-6-luna": {"input": 0.50, "output": 1.50},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "anthropic/claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
}


class LLMService:
    def __init__(self) -> None:
        self.openai_llm: ChatOpenAI | None = (
            ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=1,
                api_key=SecretStr(settings.OPENAI_API_KEY),
            )
            if settings.OPENAI_API_KEY
            else None
        )
        self.openrouter_llm: ChatOpenRouter | None = (
            ChatOpenRouter(
                model=settings.OPENROUTER_MODEL,
                temperature=0,
                max_tokens=2000,
                api_key=SecretStr(settings.OPENROUTER_API_KEY),
            )
            if settings.OPENROUTER_API_KEY
            else None
        )
        self.groq_llm: ChatOpenAI | None = (
            ChatOpenAI(
                model=settings.GROQ_MODEL,
                temperature=0,
                api_key=SecretStr(settings.GROQ_API_KEY),
                base_url="https://api.groq.com/openai/v1",
            )
            if settings.GROQ_API_KEY
            else None
        )

    @staticmethod
    def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 0.50, "output": 1.50})
        cost = (prompt_tokens / 1_000_000) * pricing["input"] + (
            completion_tokens / 1_000_000
        ) * pricing["output"]
        return round(cost, 6)

    @traceable(run_type="llm", name="Structured Extraction Call")
    async def extract_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
    ) -> tuple[T, int, float]:
        """
        Executes an LLM call enforcing strict Pydantic schema validation via LangChain
        .with_structured_output(schema, include_raw=True).
        Automatically fails over across configured providers (OpenAI -> OpenRouter -> Groq).
        Returns: (parsed_pydantic_object, total_tokens, cost_usd)
        """
        providers: list[tuple[str, Any, str]] = []
        if self.openai_llm:
            providers.append(("openai", self.openai_llm, settings.OPENAI_MODEL))
        if self.openrouter_llm:
            providers.append(("openrouter", self.openrouter_llm, settings.OPENROUTER_MODEL))
        if self.groq_llm:
            providers.append(("groq", self.groq_llm, settings.GROQ_MODEL))

        if not providers:
            raise RuntimeError("No LLM API keys configured (OpenAI, OpenRouter, or Groq required).")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        last_error: Exception | None = None
        for provider_name, llm, model_name in providers:
            try:
                structured_llm = llm.with_structured_output(schema, include_raw=True)
                result = await structured_llm.ainvoke(messages)

                parsed = result.get("parsed") if isinstance(result, dict) else result
                if parsed is None:
                    raise ValueError(f"{provider_name} returned null parsed output: {result.get('parsing_error')}")

                raw_msg = result.get("raw") if isinstance(result, dict) else None
                usage = getattr(raw_msg, "usage_metadata", None) or {}
                prompt_toks = int(usage.get("input_tokens", 0))
                comp_toks = int(usage.get("output_tokens", 0))
                total_toks = int(usage.get("total_tokens", prompt_toks + comp_toks))
                cost = self.calculate_cost(model_name, prompt_toks, comp_toks)
                return parsed, total_toks, cost

            except Exception as e:
                last_error = e
                print(f"[LLM Fallback] Provider '{provider_name}' ({model_name}) failed: {e}. Trying next...")
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


llm_service = LLMService()
