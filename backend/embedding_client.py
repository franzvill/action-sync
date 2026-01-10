"""
Embedding Client Abstraction

Provides a unified interface for OpenAI embedding providers (Azure and Direct).
"""

from typing import List, Optional
from openai import AsyncAzureOpenAI, AsyncOpenAI
from config import get_settings

settings = get_settings()


class EmbeddingClient:
    """Abstract interface for embedding generation."""
    
    def __init__(self):
        """Initialize the embedding client based on provider setting."""
        self.provider = settings.embedding_provider.lower()
        self._client = None
        self._model = None
        
        if self.provider == "openai":
            # Direct OpenAI API
            if not settings.openai_api_key:
                print("OpenAI API key not configured, embeddings will be disabled")
                return
            
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_embedding_model or "text-embedding-3-small"
            
        elif self.provider == "azure_openai":
            # Azure OpenAI API
            if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
                print("Azure OpenAI not configured, embeddings will be disabled")
                return
            
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version="2024-02-01"
            )
            self._model = settings.azure_openai_embedding_deployment or "text-embedding-3-small"
            
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}. Use 'openai' or 'azure_openai'")
    
    def is_configured(self) -> bool:
        """Check if the embedding client is properly configured."""
        return self._client is not None
    
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding, or None if not configured
        """
        if not self.is_configured():
            return None
        
        try:
            response = await self._client.embeddings.create(
                input=text,
                model=self._model
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None
    
    async def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embeddings (or None for failed embeddings)
        """
        if not self.is_configured():
            return [None] * len(texts)
        
        try:
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model
            )
            
            # Sort by index to maintain order
            embeddings = [None] * len(texts)
            for item in response.data:
                embeddings[item.index] = item.embedding
            
            return embeddings
        except Exception as e:
            print(f"Error generating embeddings batch: {e}")
            return [None] * len(texts)


# Global singleton instance
_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """
    Get the global embedding client instance.
    
    Returns:
        EmbeddingClient singleton instance
    """
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
