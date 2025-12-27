"""
Ollama Local Embeddings Provider

Uses Ollama's nomic-embed-text model for fast local embeddings.
Much faster than OpenAI API - no network latency, no rate limits.

Available models:
- nomic-embed-text (274 MB) - Good balance of speed/quality
- mxbai-embed-large (669 MB) - Higher quality, slower
"""

import requests
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"


def check_ollama_available() -> bool:
    """Check if Ollama is running and accessible"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def list_embedding_models() -> List[str]:
    """List available embedding models in Ollama"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            # Filter for embedding models
            embed_models = []
            for m in models:
                name = m.get('name', '')
                if any(x in name.lower() for x in ['embed', 'nomic', 'mxbai']):
                    embed_models.append(name)
            return embed_models
    except Exception as e:
        logger.warning(f"Could not list Ollama models: {e}")
    return []


def get_embedding(text: str, model: str = "nomic-embed-text") -> Optional[List[float]]:
    """
    Get embedding for a single text using Ollama.

    Args:
        text: Text to embed
        model: Ollama model name

    Returns:
        Embedding vector as list of floats, or None on error
    """
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": model,
                "prompt": text
            },
            timeout=30
        )

        if response.status_code == 200:
            return response.json().get('embedding')
        else:
            logger.error(f"Ollama embedding error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Ollama embedding request failed: {e}")
        return None


def get_embeddings_batch(texts: List[str], model: str = "nomic-embed-text") -> List[List[float]]:
    """
    Get embeddings for multiple texts.

    Ollama processes one at a time but locally it's still fast.

    Args:
        texts: List of texts to embed
        model: Ollama model name

    Returns:
        List of embedding vectors
    """
    embeddings = []

    for i, text in enumerate(texts):
        embedding = get_embedding(text, model)
        if embedding:
            embeddings.append(embedding)
        else:
            # Return empty vector on error (will be filtered out)
            embeddings.append([])

        # Log progress for large batches
        if (i + 1) % 50 == 0:
            logger.info(f"[Ollama] Embedded {i+1}/{len(texts)} texts")

    return embeddings


class OllamaEmbedder:
    """Ollama embedding provider matching OpenAI interface"""

    def __init__(self, model: str = "nomic-embed-text"):
        self.model = model
        self.available = check_ollama_available()

        if not self.available:
            raise RuntimeError("Ollama is not running. Start with: ollama serve")

        # Check if model is available
        models = list_embedding_models()
        if self.model not in models and f"{self.model}:latest" not in models:
            available = ', '.join(models) if models else 'none'
            raise RuntimeError(
                f"Model '{model}' not found in Ollama. "
                f"Available: {available}. "
                f"Pull with: ollama pull {model}"
            )

        self.embedding_dim = self._get_embedding_dim()
        logger.info(f"[Ollama] Using {model} (dim={self.embedding_dim})")

    def _get_embedding_dim(self) -> int:
        """Get embedding dimension by running a test embed"""
        test_embed = get_embedding("test", self.model)
        return len(test_embed) if test_embed else 768  # Default nomic dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts"""
        return get_embeddings_batch(texts, self.model)

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query"""
        return get_embedding(query, self.model)


if __name__ == "__main__":
    # Test the embeddings
    logging.basicConfig(level=logging.INFO)

    print("Checking Ollama...")
    if check_ollama_available():
        print("  Ollama is running")

        models = list_embedding_models()
        print(f"  Embedding models: {models}")

        if models:
            model = models[0]
            print(f"\nTesting {model}...")

            embedder = OllamaEmbedder(model)

            # Test single embedding
            embedding = embedder.embed_query("Division 8 windows and doors")
            print(f"  Single embedding dim: {len(embedding)}")

            # Test batch
            texts = [
                "Window schedule shows 45 double hung windows",
                "Hollow metal doors and frames per section 081113",
                "Storefront system at main entrance"
            ]
            embeddings = embedder.embed(texts)
            print(f"  Batch embeddings: {len(embeddings)} x {len(embeddings[0])}")
    else:
        print("  Ollama is not running. Start with: ollama serve")
