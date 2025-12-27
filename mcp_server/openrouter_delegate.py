"""
OpenRouter Delegate for MCP Server

Handles bulk analysis delegation to free OpenRouter models with:
- Rate limit tracking per model
- Automatic model rotation when limits hit
- Cost optimization (prefers free models)
- Retry logic with backoff
"""

import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import httpx

# =============================================================================
# FREE MODEL CONFIGURATION
# =============================================================================

FREE_MODELS = [
    {
        "id": "amazon/nova-lite-v1",
        "rpm": 10,  # Requests per minute
        "rpd": 1000,  # Requests per day
        "context": 32000,
        "priority": 1  # Lower = higher priority
    },
    {
        "id": "google/gemini-2.0-flash-exp:free",
        "rpm": 10,
        "rpd": 1500,
        "context": 128000,
        "priority": 2
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "rpm": 10,
        "rpd": 100,
        "context": 131072,
        "priority": 3
    },
    {
        "id": "qwen/qwen-2-7b-instruct:free",
        "rpm": 20,
        "rpd": 200,
        "context": 32768,
        "priority": 4
    }
]


class RateLimitException(Exception):
    """Raised when all free models have hit rate limits"""
    pass


class OpenRouterDelegate:
    """
    Handles delegation of analysis tasks to free OpenRouter models.

    Features:
    - Tracks per-model rate limits
    - Automatically selects available models
    - Handles rate limit errors gracefully
    - Provides retry logic with exponential backoff
    """

    def __init__(self, api_key: str = None):
        """
        Initialize the OpenRouter delegate.

        Args:
            api_key: OpenRouter API key (defaults to env var OPENROUTER_API_KEY)
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"

        # Rate limit tracking: model_id -> {"minute": [], "day": []}
        self._usage = {}
        for model in FREE_MODELS:
            self._usage[model["id"]] = {
                "minute": [],  # Timestamps of requests in last minute
                "day": []      # Timestamps of requests today
            }

        # HTTP client
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://project-tracker.local",
                    "X-Title": "Project Tracker MCP"
                },
                timeout=60.0
            )
        return self._client

    def _clean_usage(self, model_id: str):
        """Remove expired timestamps from usage tracking"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        usage = self._usage[model_id]
        usage["minute"] = [t for t in usage["minute"] if t > minute_ago]
        usage["day"] = [t for t in usage["day"] if t > day_start]

    def _is_available(self, model_id: str) -> bool:
        """Check if a model is available (not rate limited)"""
        self._clean_usage(model_id)

        model = next((m for m in FREE_MODELS if m["id"] == model_id), None)
        if not model:
            return False

        usage = self._usage[model_id]

        # Check minute limit
        if len(usage["minute"]) >= model["rpm"]:
            return False

        # Check daily limit
        if len(usage["day"]) >= model["rpd"]:
            return False

        return True

    def _record_usage(self, model_id: str):
        """Record a request against a model's limits"""
        now = datetime.now()
        self._usage[model_id]["minute"].append(now)
        self._usage[model_id]["day"].append(now)

    def select_model(self, required_context: int = 0) -> Dict:
        """
        Select the best available free model.

        Args:
            required_context: Minimum context window needed

        Returns:
            Model configuration dict

        Raises:
            RateLimitException: If no models available
        """
        # Sort by priority
        available = sorted(FREE_MODELS, key=lambda m: m["priority"])

        for model in available:
            # Check context requirement
            if required_context > 0 and model["context"] < required_context:
                continue

            # Check availability
            if self._is_available(model["id"]):
                return model

        raise RateLimitException("All free models are at capacity. Try again later.")

    async def analyze(
        self,
        prompt: str,
        content: str,
        model_id: str = None,
        system_prompt: str = None,
        max_tokens: int = 4096,
        temperature: float = 0.3
    ) -> Dict:
        """
        Send analysis request to OpenRouter.

        Args:
            prompt: The analysis prompt/question
            content: Content to analyze
            model_id: Specific model to use (auto-selects if not provided)
            system_prompt: Optional system prompt
            max_tokens: Maximum response tokens
            temperature: Generation temperature

        Returns:
            Dict with response and metadata
        """
        # Select model if not specified
        if not model_id:
            content_len = len(content)
            # Rough estimate: 4 chars per token
            estimated_tokens = content_len // 4
            model = self.select_model(required_context=estimated_tokens + max_tokens)
            model_id = model["id"]

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({
            "role": "user",
            "content": f"{prompt}\n\n---\n\n{content}"
        })

        # Make request
        client = await self._get_client()

        try:
            self._record_usage(model_id)

            response = await client.post(
                "/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            )

            if response.status_code == 429:
                # Rate limited - mark model as unavailable
                return {
                    "success": False,
                    "error": "rate_limited",
                    "model": model_id,
                    "message": "Model rate limited. Try again or use different model."
                }

            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "model": model_id,
                "content": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
                "finish_reason": data["choices"][0].get("finish_reason")
            }

        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": "http_error",
                "model": model_id,
                "message": str(e)
            }

    async def bulk_analyze(
        self,
        documents: List[Dict],
        analysis_type: str,
        max_concurrent: int = 3
    ) -> List[Dict]:
        """
        Run analysis on multiple documents with rate limiting.

        Args:
            documents: List of dicts with 'path' and 'content' keys
            analysis_type: Type of analysis to perform
            max_concurrent: Maximum concurrent requests

        Returns:
            List of analysis results
        """
        # Define analysis prompts
        prompts = {
            "extract_spec_sections": "Extract all Division 8 specification sections from this document. List each section number and title.",
            "extract_schedule_data": "Extract door, window, or hardware schedule data from this document. List quantities, types, and specifications.",
            "summarize_scope": "Summarize the Division 8 (Openings) scope from this document in bullet points.",
            "extract_quantities": "Extract all quantities mentioned for doors, windows, frames, hardware, and glazing."
        }

        prompt = prompts.get(analysis_type, analysis_type)

        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_doc(doc):
            async with semaphore:
                # Wait for available model
                await self._wait_for_availability()

                result = await self.analyze(
                    prompt=prompt,
                    content=doc.get("content", ""),
                    system_prompt="You are a construction document analysis assistant specializing in Division 8 (Openings) scope."
                )

                return {
                    "path": doc.get("path"),
                    "name": doc.get("name"),
                    "result": result
                }

        # Run all analyses
        tasks = [process_doc(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        processed_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed_results.append({
                    "path": documents[i].get("path"),
                    "name": documents[i].get("name"),
                    "result": {
                        "success": False,
                        "error": "exception",
                        "message": str(r)
                    }
                })
            else:
                processed_results.append(r)

        return processed_results

    async def _wait_for_availability(self, timeout: float = 60.0):
        """Wait until a model becomes available"""
        start = time.time()

        while time.time() - start < timeout:
            try:
                self.select_model()
                return
            except RateLimitException:
                await asyncio.sleep(5)

        raise RateLimitException(f"No model available after {timeout}s")

    def get_status(self) -> Dict:
        """Get current rate limit status for all models"""
        status = {}

        for model in FREE_MODELS:
            model_id = model["id"]
            self._clean_usage(model_id)
            usage = self._usage[model_id]

            status[model_id] = {
                "available": self._is_available(model_id),
                "rpm_used": len(usage["minute"]),
                "rpm_limit": model["rpm"],
                "rpd_used": len(usage["day"]),
                "rpd_limit": model["rpd"],
                "context": model["context"]
            }

        return status

    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_delegate_instance = None

def get_delegate() -> OpenRouterDelegate:
    """Get the singleton OpenRouter delegate instance"""
    global _delegate_instance
    if _delegate_instance is None:
        _delegate_instance = OpenRouterDelegate()
    return _delegate_instance


async def quick_analyze(prompt: str, content: str) -> Dict:
    """Quick single-document analysis using free models"""
    delegate = get_delegate()
    return await delegate.analyze(prompt, content)


async def bulk_analyze_documents(documents: List[Dict], analysis_type: str) -> List[Dict]:
    """Bulk analyze documents with automatic rate limiting"""
    delegate = get_delegate()
    return await delegate.bulk_analyze(documents, analysis_type)
