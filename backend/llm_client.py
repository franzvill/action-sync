"""
LLM Client Abstraction

Provides a unified interface for Anthropic LLM providers (Azure and Direct).
"""

from typing import Dict, Optional
from config import get_settings

settings = get_settings()


def get_llm_config() -> Dict[str, str]:
    """
    Get LLM configuration based on the provider setting.
    
    Returns:
        Dict with 'base_url', 'api_key', and 'model' keys.
    """
    provider = settings.llm_provider.lower()
    
    if provider == "anthropic":
        # Direct Anthropic API
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        
        return {
            "base_url": "",  # Empty for direct API (uses default)
            "api_key": settings.anthropic_api_key,
            "model": settings.anthropic_model or "claude-opus-4-20250514"
        }
    
    elif provider == "azure_anthropic":
        # Azure Anthropic API
        if not settings.azure_anthropic_endpoint or not settings.azure_anthropic_api_key:
            raise ValueError("AZURE_ANTHROPIC_ENDPOINT and AZURE_ANTHROPIC_API_KEY are required when LLM_PROVIDER=azure_anthropic")
        
        return {
            "base_url": settings.azure_anthropic_endpoint,
            "api_key": settings.azure_anthropic_api_key,
            "model": settings.azure_anthropic_model or "claude-opus-4-5"
        }
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Use 'anthropic' or 'azure_anthropic'")


def get_llm_env() -> Dict[str, str]:
    """
    Get environment variables for Claude SDK based on provider.
    
    Returns:
        Dict with environment variables to pass to Claude SDK.
    """
    config = get_llm_config()
    
    env = {
        "ANTHROPIC_API_KEY": config["api_key"]
    }
    
    # Only set base URL if it's not empty (Azure case)
    if config["base_url"]:
        env["ANTHROPIC_BASE_URL"] = config["base_url"]
    
    return env


def get_llm_model() -> str:
    """
    Get the model name to use for LLM requests.
    
    Returns:
        Model name string.
    """
    config = get_llm_config()
    return config["model"]
