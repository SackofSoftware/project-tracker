"""
AI Provider Management for Pipeline

Supports:
- OpenAI GPT-5 nano (vision capable) - for image analysis
- DeepSeek V3.2 Speciale via OpenRouter (text-only) - PRIMARY for reasoning
- GPT-OSS-120B via OpenRouter (FREE) - for batch file classification

Strategy:
- Use DeepSeek for all text-based reasoning tasks (163K context, excellent reasoning)
- Use GPT-5 nano only when vision is required (cover sheets, ambiguous schedules)
- Use GPT-OSS-120B (free tier) for batch operations to save costs
"""

import os
import json
import base64
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    """Standardized AI response"""
    success: bool
    data: Dict
    model: str
    tokens_used: int
    error: Optional[str] = None
    raw_response: Optional[str] = None


class GPT5NanoProvider:
    """
    OpenAI GPT-5 nano provider for VISION tasks only.

    Pricing:
    - Input: $0.05/1M tokens
    - Output: $0.40/1M tokens
    - Cached input: $0.025/1M tokens (50% discount)

    Use for: Cover sheet analysis, schedule images where text extraction fails
    """

    MODEL = "gpt-5-nano"
    BASE_URL = "https://api.openai.com/v1"

    # System prompts for caching
    SYSTEM_PROMPTS = {
        'cover_sheet': """You are analyzing construction project cover sheets.
Extract the official project name/title from the document.
Look for: project title in title block, header, or prominent text.
Return valid JSON only.""",

        'schedule_analysis': """You are analyzing construction schedules.
Extract all entries with: mark/number, type, material, size, notes.
Classify doors as: METAL (HM, aluminum, stainless) or WOOD (note as exclusion).
Return valid JSON only.""",
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API key found - GPT-5 nano unavailable")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def vision_query(
        self,
        image_base64: str,
        prompt: str,
        system_prompt_key: str = None,
        max_tokens: int = 4096
    ) -> AIResponse:
        """
        Query GPT-5 nano with an image.

        Args:
            image_base64: Base64 encoded image (JPEG/PNG)
            prompt: User prompt
            system_prompt_key: Key to cached system prompt (for cost savings)
            max_tokens: Max response tokens
        """
        if not self.is_available:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="OpenAI API key not configured"
            )

        messages = []

        # Add cached system prompt if specified
        if system_prompt_key and system_prompt_key in self.SYSTEM_PROMPTS:
            messages.append({
                "role": "system",
                "content": self.SYSTEM_PROMPTS[system_prompt_key]
            })

        # Add user message with image
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}",
                        "detail": "high"  # Use high detail for schedules
                    }
                }
            ]
        })

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": messages,
                        "max_completion_tokens": max_tokens,
                        "response_format": {"type": "json_object"}
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        return AIResponse(
                            success=False,
                            data={},
                            model=self.MODEL,
                            tokens_used=0,
                            error=result.get('error', {}).get('message', str(result))
                        )

                    content = result['choices'][0]['message']['content']
                    tokens = result.get('usage', {}).get('total_tokens', 0)

                    # Parse JSON response
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        data = {"raw_text": content}

                    return AIResponse(
                        success=True,
                        data=data,
                        model=self.MODEL,
                        tokens_used=tokens,
                        raw_response=content
                    )

        except asyncio.TimeoutError:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="Request timed out"
            )
        except Exception as e:
            logger.error(f"GPT-5 nano error: {e}")
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=str(e)
            )

    async def text_query(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 4096
    ) -> AIResponse:
        """Text-only query (use DeepSeek instead when possible)"""
        if not self.is_available:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="OpenAI API key not configured"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": messages,
                        "max_completion_tokens": max_tokens,
                        "response_format": {"type": "json_object"}
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        return AIResponse(
                            success=False,
                            data={},
                            model=self.MODEL,
                            tokens_used=0,
                            error=result.get('error', {}).get('message', str(result))
                        )

                    content = result['choices'][0]['message']['content']
                    tokens = result.get('usage', {}).get('total_tokens', 0)

                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        data = {"raw_text": content}

                    return AIResponse(
                        success=True,
                        data=data,
                        model=self.MODEL,
                        tokens_used=tokens,
                        raw_response=content
                    )

        except Exception as e:
            logger.error(f"GPT-5 nano text error: {e}")
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=str(e)
            )


class DeepSeekProvider:
    """
    DeepSeek V3.2 Speciale via OpenRouter - PRIMARY reasoning model.

    Text-only (no vision), but excellent for:
    - Complex reasoning tasks
    - Large document analysis (163K context)
    - Chain-of-thought with <think> tags

    Pricing:
    - Input: $0.27/1M tokens
    - Output: $0.41/1M tokens

    NOTE: Expires Dec 15, 2025 - use heavily while available!
    """

    MODEL = "deepseek/deepseek-v3.2-speciale"
    BASE_URL = "https://openrouter.ai/api/v1"
    CONTEXT_LIMIT = 163_000
    EXPIRY_DATE = "2025-12-15"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("No OpenRouter API key found - DeepSeek unavailable")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def is_expired(self) -> bool:
        """Check if model access has expired"""
        expiry = datetime.strptime(self.EXPIRY_DATE, "%Y-%m-%d")
        return datetime.now() > expiry

    async def query(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 8192,
        use_reasoning: bool = True
    ) -> AIResponse:
        """
        Query DeepSeek for text-based reasoning.

        Args:
            prompt: User prompt (can be very long - 163K context!)
            system_prompt: Optional system prompt
            max_tokens: Max response tokens (up to 65536)
            use_reasoning: Enable chain-of-thought with <think> tags
        """
        if not self.is_available:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="OpenRouter API key not configured"
            )

        if self.is_expired:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=f"DeepSeek V3.2 Speciale access expired on {self.EXPIRY_DATE}"
            )

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add reasoning instruction if enabled
        if use_reasoning:
            reasoning_prompt = """Think through this step-by-step. Use <think> tags for your reasoning process, then provide your final answer in valid JSON format.

"""
            prompt = reasoning_prompt + prompt

        messages.append({"role": "user", "content": prompt})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://project-tracker.local",
                        "X-Title": "Project Tracker Pipeline"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": messages,
                        "max_completion_tokens": max_tokens,
                    },
                    timeout=aiohttp.ClientTimeout(total=180)  # Longer timeout for reasoning
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        error_msg = result.get('error', {})
                        if isinstance(error_msg, dict):
                            error_msg = error_msg.get('message', str(result))
                        return AIResponse(
                            success=False,
                            data={},
                            model=self.MODEL,
                            tokens_used=0,
                            error=str(error_msg)
                        )

                    content = result['choices'][0]['message']['content']
                    tokens = result.get('usage', {}).get('total_tokens', 0)

                    # Extract JSON from response (may be after <think> tags)
                    data = self._extract_json(content)

                    return AIResponse(
                        success=True,
                        data=data,
                        model=self.MODEL,
                        tokens_used=tokens,
                        raw_response=content
                    )

        except asyncio.TimeoutError:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="Request timed out (180s)"
            )
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=str(e)
            )

    def _extract_json(self, content: str) -> Dict:
        """Extract JSON from response, handling <think> tags"""
        # Remove think tags if present
        import re

        # Try to find JSON after closing </think> tag
        if '</think>' in content:
            parts = content.split('</think>')
            content = parts[-1].strip()

        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        # Try to find raw JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_text": content, "parse_failed": True}


class DeepSeekV32Provider:
    """
    DeepSeek V3.2 via OpenRouter - PRIMARY model for unified pipeline.

    Text-only (no vision), excellent for:
    - Division 8 scope extraction
    - Complex document analysis
    - Structured JSON output
    - Large context (128K tokens)

    Pricing:
    - Input: $0.27/1M tokens
    - Output: $1.10/1M tokens

    This is the user-specified model for the unified AI pipeline.
    """

    MODEL = "deepseek/deepseek-v3.2"
    BASE_URL = "https://openrouter.ai/api/v1"
    CONTEXT_LIMIT = 128_000

    # Division 8 extraction system prompt
    DIV8_SYSTEM_PROMPT = """You are a construction document analyst specializing in Division 8 (Openings).
Your task is to extract scope information from specifications and drawings.

Division 8 categories to identify:
- 08 11 00: Metal Doors and Frames
- 08 14 00: Wood Doors
- 08 31 00: Access Doors and Panels
- 08 41 00: Entrances and Storefronts
- 08 43 00: Storefronts
- 08 44 00: Curtain Wall and Glazed Assemblies
- 08 51 00: Metal Windows
- 08 52 00: Wood Windows
- 08 71 00: Door Hardware
- 08 80 00: Glazing

For each item found, extract:
- Type/category
- Quantity (if available from schedules)
- Specifications (material, finish, size)
- Special requirements
- Related specification sections

Return well-structured JSON with clear categorization."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("No OpenRouter API key found - DeepSeek V3.2 unavailable")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def query(
        self,
        prompt: str,
        context: str = "",
        system_prompt: str = None,
        max_tokens: int = 8192,
        temperature: float = 0.2
    ) -> AIResponse:
        """
        Query DeepSeek V3.2 for text-based analysis.

        Args:
            prompt: The analysis prompt/question
            context: Document content to analyze (can be very large - 128K context)
            system_prompt: Optional system prompt (defaults to DIV8_SYSTEM_PROMPT)
            max_tokens: Max response tokens
            temperature: Generation temperature (lower = more focused)
        """
        if not self.is_available:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="OpenRouter API key not configured"
            )

        messages = []

        # Use provided system prompt or default Division 8 prompt
        sys_prompt = system_prompt or self.DIV8_SYSTEM_PROMPT
        messages.append({"role": "system", "content": sys_prompt})

        # Build user message with context
        if context:
            user_content = f"{prompt}\n\n---\n\nDocument Content:\n{context}"
        else:
            user_content = prompt

        messages.append({"role": "user", "content": user_content})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://project-tracker.local",
                        "X-Title": "Project Tracker Unified Pipeline"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        error_msg = result.get('error', {})
                        if isinstance(error_msg, dict):
                            error_msg = error_msg.get('message', str(result))
                        return AIResponse(
                            success=False,
                            data={},
                            model=self.MODEL,
                            tokens_used=0,
                            error=str(error_msg)
                        )

                    content = result['choices'][0]['message']['content']
                    tokens = result.get('usage', {}).get('total_tokens', 0)

                    # Extract JSON from response
                    data = self._extract_json(content)

                    return AIResponse(
                        success=True,
                        data=data,
                        model=self.MODEL,
                        tokens_used=tokens,
                        raw_response=content
                    )

        except asyncio.TimeoutError:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="Request timed out (180s)"
            )
        except Exception as e:
            logger.error(f"DeepSeek V3.2 error: {e}")
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=str(e)
            )

    async def extract_division8_scope(
        self,
        spec_content: str,
        schedule_content: str = "",
        drawing_notes: str = ""
    ) -> AIResponse:
        """
        Specialized method for Division 8 scope extraction.

        Args:
            spec_content: Division 8 specification text
            schedule_content: Door/window schedule data (optional)
            drawing_notes: Notes from architectural drawings (optional)
        """
        prompt = """Analyze the provided construction documents and extract all Division 8 (Openings) scope.

For each category found, provide:
1. Specification section number and title
2. Products/materials specified
3. Quantities (from schedules if available)
4. Special requirements or exclusions
5. Related specification sections

Format your response as JSON with this structure:
{
    "doors": {
        "metal_doors_frames": {...},
        "wood_doors": {...},
        "access_doors": {...}
    },
    "windows": {
        "aluminum_windows": {...},
        "wood_windows": {...}
    },
    "storefronts_curtainwall": {
        "storefronts": {...},
        "curtain_wall": {...}
    },
    "hardware": {...},
    "glazing": {...},
    "exclusions": [...],
    "summary": {
        "total_doors": 0,
        "total_windows": 0,
        "key_items": [...]
    }
}"""

        # Build context from all sources
        context_parts = []
        if spec_content:
            context_parts.append(f"=== SPECIFICATIONS ===\n{spec_content}")
        if schedule_content:
            context_parts.append(f"=== SCHEDULES ===\n{schedule_content}")
        if drawing_notes:
            context_parts.append(f"=== DRAWING NOTES ===\n{drawing_notes}")

        context = "\n\n".join(context_parts)

        return await self.query(
            prompt=prompt,
            context=context,
            max_tokens=16384  # Larger for comprehensive extraction
        )

    def _extract_json(self, content: str) -> Dict:
        """Extract JSON from response"""
        import re

        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        # Try to find raw JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_text": content, "parse_failed": True}


class GPTOSSProvider:
    """
    GPT-OSS-120B via OpenRouter - FREE tier for batch operations.

    Best for:
    - File classification (drawing vs spec vs quote)
    - Simple text extraction
    - Batch operations where cost matters

    Limitations:
    - No vision capability
    - Rate limited on free tier
    - Smaller context than DeepSeek

    Model: openai/gpt-oss-120b:free
    """

    MODEL = "openai/gpt-oss-120b:free"
    BASE_URL = "https://openrouter.ai/api/v1"
    CONTEXT_LIMIT = 32_000

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("No OpenRouter API key found - GPT-OSS unavailable")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def query(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 4096
    ) -> AIResponse:
        """
        Query GPT-OSS-120B for text-based tasks.

        Args:
            prompt: User prompt (up to 32K context)
            system_prompt: Optional system prompt
            max_tokens: Max response tokens
        """
        if not self.is_available:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="OpenRouter API key not configured"
            )

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://project-tracker.local",
                        "X-Title": "Project Tracker Batch"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        error_msg = result.get('error', {})
                        if isinstance(error_msg, dict):
                            error_msg = error_msg.get('message', str(result))
                        return AIResponse(
                            success=False,
                            data={},
                            model=self.MODEL,
                            tokens_used=0,
                            error=str(error_msg)
                        )

                    content = result['choices'][0]['message']['content']
                    tokens = result.get('usage', {}).get('total_tokens', 0)

                    # Extract JSON from response
                    data = self._extract_json(content)

                    return AIResponse(
                        success=True,
                        data=data,
                        model=self.MODEL,
                        tokens_used=tokens,
                        raw_response=content
                    )

        except asyncio.TimeoutError:
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error="Request timed out (120s)"
            )
        except Exception as e:
            logger.error(f"GPT-OSS error: {e}")
            return AIResponse(
                success=False,
                data={},
                model=self.MODEL,
                tokens_used=0,
                error=str(e)
            )

    def _extract_json(self, content: str) -> Dict:
        """Extract JSON from response"""
        import re

        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        # Try to find raw JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_text": content, "parse_failed": True}


class AIProviderManager:
    """
    Manages AI providers with automatic fallback.

    Strategy:
    - DeepSeek V3.2: PRIMARY for unified pipeline (Division 8 extraction)
    - DeepSeek V3.2 Speciale: For complex reasoning tasks (expires Dec 15, 2025)
    - GPT-5 nano: Only for vision tasks (image analysis)
    - GPT-OSS-120B: FREE tier for batch operations (file classification)
    """

    def __init__(self):
        # Load API keys
        openai_key = os.getenv("OPENAI_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        self.gpt5_nano = GPT5NanoProvider(openai_key)
        self.deepseek = DeepSeekProvider(openrouter_key)
        self.deepseek_v32 = DeepSeekV32Provider(openrouter_key)  # PRIMARY for unified pipeline
        self.gpt_oss = GPTOSSProvider(openrouter_key)

        # Track usage for cost estimation
        self.usage_stats = {
            "gpt5_nano_tokens": 0,
            "deepseek_tokens": 0,
            "deepseek_v32_tokens": 0,
            "gpt_oss_tokens": 0,
            "gpt5_nano_calls": 0,
            "deepseek_calls": 0,
            "deepseek_v32_calls": 0,
            "gpt_oss_calls": 0,
        }

    @property
    def has_vision(self) -> bool:
        return self.gpt5_nano.is_available

    @property
    def has_reasoning(self) -> bool:
        return self.deepseek.is_available and not self.deepseek.is_expired

    @property
    def has_unified_pipeline(self) -> bool:
        """Check if DeepSeek V3.2 is available for unified pipeline"""
        return self.deepseek_v32.is_available

    @property
    def has_free_llm(self) -> bool:
        return self.gpt_oss.is_available

    async def classify_free(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 2048
    ) -> AIResponse:
        """
        Execute a classification task using DeepSeek V3.2 Speciale.
        Very cheap (~$0.14/M input, $0.28/M output) and reliable.
        """
        # Use DeepSeek directly (cheap and reliable)
        if self.has_reasoning:
            result = await self.deepseek.query(prompt, system_prompt, max_tokens, use_reasoning=False)
            if result.success:
                self.usage_stats["deepseek_tokens"] += result.tokens_used
                self.usage_stats["deepseek_calls"] += 1
            return result

        # Fallback to GPT-OSS if DeepSeek unavailable
        if self.has_free_llm:
            result = await self.gpt_oss.query(prompt, system_prompt, max_tokens)
            if result.success:
                self.usage_stats["gpt_oss_tokens"] += result.tokens_used
                self.usage_stats["gpt_oss_calls"] += 1
                return result
            logger.warning(f"GPT-OSS failed: {result.error}")

        return AIResponse(
            success=False,
            data={},
            model="none",
            tokens_used=0,
            error="No AI providers available for classification"
        )

    async def reason(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 8192
    ) -> AIResponse:
        """
        Execute a reasoning task - uses DeepSeek (preferred) or GPT-5 nano fallback.
        """
        # Try DeepSeek first (better for reasoning)
        if self.has_reasoning:
            result = await self.deepseek.query(prompt, system_prompt, max_tokens)
            if result.success:
                self.usage_stats["deepseek_tokens"] += result.tokens_used
                self.usage_stats["deepseek_calls"] += 1
                return result
            logger.warning(f"DeepSeek failed: {result.error}, trying GPT-5 nano")

        # Fallback to GPT-5 nano
        if self.gpt5_nano.is_available:
            result = await self.gpt5_nano.text_query(prompt, system_prompt, max_tokens)
            if result.success:
                self.usage_stats["gpt5_nano_tokens"] += result.tokens_used
                self.usage_stats["gpt5_nano_calls"] += 1
            return result

        return AIResponse(
            success=False,
            data={},
            model="none",
            tokens_used=0,
            error="No AI providers available"
        )

    async def vision(
        self,
        image_base64: str,
        prompt: str,
        system_prompt_key: str = None,
        max_tokens: int = 4096
    ) -> AIResponse:
        """
        Execute a vision task - requires GPT-5 nano (DeepSeek has no vision).
        """
        if not self.has_vision:
            return AIResponse(
                success=False,
                data={},
                model="none",
                tokens_used=0,
                error="No vision-capable AI available (GPT-5 nano required)"
            )

        result = await self.gpt5_nano.vision_query(
            image_base64, prompt, system_prompt_key, max_tokens
        )

        if result.success:
            self.usage_stats["gpt5_nano_tokens"] += result.tokens_used
            self.usage_stats["gpt5_nano_calls"] += 1

        return result

    async def extract_division8(
        self,
        spec_content: str,
        schedule_content: str = "",
        drawing_notes: str = ""
    ) -> AIResponse:
        """
        Execute Division 8 scope extraction using DeepSeek V3.2.
        This is the PRIMARY method for the unified analysis pipeline.

        Args:
            spec_content: Division 8 specification text
            schedule_content: Door/window schedule data (optional)
            drawing_notes: Notes from architectural drawings (optional)
        """
        if not self.has_unified_pipeline:
            return AIResponse(
                success=False,
                data={},
                model="none",
                tokens_used=0,
                error="DeepSeek V3.2 not available for unified pipeline"
            )

        result = await self.deepseek_v32.extract_division8_scope(
            spec_content=spec_content,
            schedule_content=schedule_content,
            drawing_notes=drawing_notes
        )

        if result.success:
            self.usage_stats["deepseek_v32_tokens"] += result.tokens_used
            self.usage_stats["deepseek_v32_calls"] += 1

        return result

    async def unified_query(
        self,
        prompt: str,
        context: str = "",
        system_prompt: str = None,
        max_tokens: int = 8192
    ) -> AIResponse:
        """
        General query using DeepSeek V3.2 for unified pipeline.
        Use for custom queries beyond standard Division 8 extraction.
        """
        if not self.has_unified_pipeline:
            # Fallback to speciale if v3.2 unavailable
            if self.has_reasoning:
                full_prompt = f"{prompt}\n\n{context}" if context else prompt
                result = await self.deepseek.query(full_prompt, system_prompt, max_tokens)
                if result.success:
                    self.usage_stats["deepseek_tokens"] += result.tokens_used
                    self.usage_stats["deepseek_calls"] += 1
                return result

            return AIResponse(
                success=False,
                data={},
                model="none",
                tokens_used=0,
                error="No DeepSeek provider available"
            )

        result = await self.deepseek_v32.query(
            prompt=prompt,
            context=context,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )

        if result.success:
            self.usage_stats["deepseek_v32_tokens"] += result.tokens_used
            self.usage_stats["deepseek_v32_calls"] += 1

        return result

    def get_usage_report(self) -> Dict:
        """Get usage statistics and estimated costs"""
        # Pricing per 1M tokens
        gpt5_input_cost = 0.05 / 1_000_000
        gpt5_output_cost = 0.40 / 1_000_000
        deepseek_input_cost = 0.27 / 1_000_000
        deepseek_output_cost = 0.41 / 1_000_000
        # DeepSeek V3.2 pricing (slightly different from speciale)
        deepseek_v32_input_cost = 0.27 / 1_000_000
        deepseek_v32_output_cost = 1.10 / 1_000_000
        # GPT-OSS is FREE
        gpt_oss_cost = 0

        # Rough estimate (assuming 50/50 input/output split)
        gpt5_avg_cost = (gpt5_input_cost + gpt5_output_cost) / 2
        deepseek_avg_cost = (deepseek_input_cost + deepseek_output_cost) / 2
        deepseek_v32_avg_cost = (deepseek_v32_input_cost + deepseek_v32_output_cost) / 2

        return {
            "gpt5_nano": {
                "tokens": self.usage_stats["gpt5_nano_tokens"],
                "calls": self.usage_stats["gpt5_nano_calls"],
                "estimated_cost": self.usage_stats["gpt5_nano_tokens"] * gpt5_avg_cost,
            },
            "deepseek": {
                "tokens": self.usage_stats["deepseek_tokens"],
                "calls": self.usage_stats["deepseek_calls"],
                "estimated_cost": self.usage_stats["deepseek_tokens"] * deepseek_avg_cost,
            },
            "deepseek_v32": {
                "tokens": self.usage_stats["deepseek_v32_tokens"],
                "calls": self.usage_stats["deepseek_v32_calls"],
                "estimated_cost": self.usage_stats["deepseek_v32_tokens"] * deepseek_v32_avg_cost,
                "model": "deepseek/deepseek-v3.2",
            },
            "gpt_oss": {
                "tokens": self.usage_stats["gpt_oss_tokens"],
                "calls": self.usage_stats["gpt_oss_calls"],
                "estimated_cost": 0,  # FREE!
            },
            "total_estimated_cost": (
                self.usage_stats["gpt5_nano_tokens"] * gpt5_avg_cost +
                self.usage_stats["deepseek_tokens"] * deepseek_avg_cost +
                self.usage_stats["deepseek_v32_tokens"] * deepseek_v32_avg_cost
            )
        }
