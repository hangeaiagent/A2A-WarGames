"""
LLM Provider Presets
--------------------
Quick-setup configurations for popular LLM providers.
Served by GET /api/settings/presets and surfaced as clickable cards
on the Settings page so users can one-click fill the base_url field.

``is_native`` marks providers that are handled by a dedicated SDK
adapter inside llm_client.py rather than the generic OAI-compatible
httpx path (e.g. Anthropic).
"""

from typing import Optional

PROVIDER_PRESETS: list[dict] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "icon": "🤖",
        "base_url": "https://api.openai.com/v1",
        "placeholder_model": "gpt-4o",
        "auth_hint": "sk-… from platform.openai.com",
        "notes": (
            "Official OpenAI API. Supports GPT-4o, GPT-4o-mini, o1, o3-mini, etc. "
            "Set your API key from platform.openai.com/api-keys."
        ),
        "is_native": False,
        "docs_url": "https://platform.openai.com/docs",
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "icon": "🧠",
        "base_url": "https://api.anthropic.com/v1",
        "placeholder_model": "claude-opus-4-5",
        "auth_hint": "sk-ant-… from console.anthropic.com",
        "notes": (
            "Native Anthropic SDK — no proxy needed. "
            "Supports Claude 3.5/3.7, claude-opus-4-5, extended thinking, and tool use. "
            "Obtain your API key from console.anthropic.com/settings/keys."
        ),
        "is_native": True,
        "docs_url": "https://docs.anthropic.com",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "icon": "🔍",
        "base_url": "https://api.deepseek.com/v1",
        "placeholder_model": "deepseek-chat",
        "auth_hint": "API key from platform.deepseek.com",
        "notes": (
            "OAI-compatible endpoint. Supports deepseek-chat (V3) and "
            "deepseek-reasoner (R1 with chain-of-thought). "
            "Get your key at platform.deepseek.com."
        ),
        "is_native": False,
        "docs_url": "https://platform.deepseek.com/docs",
    },
    {
        "id": "groq",
        "label": "Groq",
        "icon": "⚡",
        "base_url": "https://api.groq.com/openai/v1",
        "placeholder_model": "llama-3.3-70b-versatile",
        "auth_hint": "gsk_… from console.groq.com",
        "notes": (
            "Ultra-fast inference via GroqChip. OAI-compatible. "
            "Supports Llama 3.x, Mixtral, Gemma 2, and more. "
            "Free tier available at console.groq.com."
        ),
        "is_native": False,
        "docs_url": "https://console.groq.com/docs",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "icon": "🌐",
        "base_url": "https://openrouter.ai/api/v1",
        "placeholder_model": "meta-llama/llama-3.3-70b-instruct",
        "auth_hint": "sk-or-… from openrouter.ai/keys",
        "notes": (
            "Multi-provider OAI-compatible gateway with 300+ models including "
            "Claude, GPT-4, Gemini, Llama, Mistral, and more. "
            "Unified billing and fallback routing."
        ),
        "is_native": False,
        "docs_url": "https://openrouter.ai/docs",
    },
    {
        "id": "mistral",
        "label": "Mistral AI",
        "icon": "💨",
        "base_url": "https://api.mistral.ai/v1",
        "placeholder_model": "mistral-large-latest",
        "auth_hint": "API key from console.mistral.ai",
        "notes": (
            "Official Mistral AI endpoint. OAI-compatible. "
            "Supports Mistral Large, Codestral, Pixtral, and Mixtral variants."
        ),
        "is_native": False,
        "docs_url": "https://docs.mistral.ai",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "icon": "🦙",
        "base_url": "http://localhost:11434/v1",
        "placeholder_model": "llama3.2",
        "auth_hint": "No API key needed for local Ollama",
        "notes": (
            "Run open-source models locally. Install Ollama from ollama.com, "
            "then pull a model: `ollama pull llama3.2`. "
            "No internet or API key required."
        ),
        "is_native": False,
        "docs_url": "https://ollama.com/library",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio (local)",
        "icon": "🖥️",
        "base_url": "http://localhost:1234/v1",
        "placeholder_model": "local-model",
        "auth_hint": "No API key needed — LM Studio serves locally",
        "notes": (
            "Run GGUF / GGML models locally via LM Studio. "
            "Start LM Studio, load a model, and enable the local server. "
            "The server listens on port 1234 by default."
        ),
        "is_native": False,
        "docs_url": "https://lmstudio.ai/docs",
    },
    {
        "id": "azure_openai",
        "label": "Azure OpenAI",
        "icon": "☁️",
        "base_url": "",
        "placeholder_model": "gpt-4o",
        "auth_hint": "Azure OpenAI key from Azure portal",
        "notes": (
            "Azure-hosted OpenAI models. Your base_url is: "
            "https://{resource}.openai.azure.com/openai/deployments/{deployment}/. "
            "Replace {resource} and {deployment} with your Azure resource name and deployment name."
        ),
        "is_native": False,
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
    },
    {
        "id": "litellm",
        "label": "LiteLLM Proxy",
        "icon": "🔄",
        "base_url": "http://localhost:4000/v1",
        "placeholder_model": "claude-opus-4-5",
        "auth_hint": "LiteLLM proxy master key",
        "notes": (
            "Self-hosted OAI-compatible proxy that can route to Anthropic, "
            "Cohere, Bedrock, and 100+ providers. Use this if you prefer a "
            "proxy over the native Anthropic SDK integration."
        ),
        "is_native": False,
        "docs_url": "https://docs.litellm.ai",
    },
]


def get_presets() -> list[dict]:
    """Return the full list of provider presets (without sensitive fields)."""
    return PROVIDER_PRESETS


# Backward-compatibility alias — allows `from provider_presets import get_provider_presets`
get_provider_presets = get_presets


def get_preset_by_id(provider_id: str) -> dict | None:
    """Return a single preset by its ID, or None."""
    for p in PROVIDER_PRESETS:
        if p["id"] == provider_id:
            return p
    return None
