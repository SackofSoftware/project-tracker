"""
Multi-agent extraction system for Division 8 project data
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import base64
import subprocess
import tempfile

import requests

from .config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL,
    DIV8_SECTIONS, MAX_WORKERS
)
from .rag_engine import RAGEngine, DocumentProcessor

# Import CSI service for enrichment (optional - graceful degradation)
try:
    from modules.csi import (
        CSIService,
        get_section_info,
        enrich_scope_with_csi,
        match_manufacturers,
        extract_section_references,
        categorize_section
    )
    CSI_AVAILABLE = True
except ImportError:
    CSI_AVAILABLE = False


@dataclass
class ExtractionResult:
    """Result from an extraction agent"""
    agent_name: str
    success: bool
    data: Dict
    error: Optional[str] = None
    tokens_used: int = 0


@dataclass
class StreamMessage:
    """Message for streaming UI updates"""
    agent: str
    message: str
    progress: float = 0.0
    data: Optional[Dict] = None
    is_complete: bool = False


class LLMClient:
    """OpenRouter LLM client with async support"""

    def __init__(self, api_key: str = OPENROUTER_API_KEY,
                 model: str = LLM_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = OPENROUTER_BASE_URL
        self._executor = ThreadPoolExecutor(max_workers=4)

    def _sync_chat(self, messages: List[Dict], temperature: float = 0.1,
                   max_tokens: int = 4096) -> str:
        """Synchronous chat request"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://div8-analyzer.local",
            "X-Title": "Division 8 Analyzer"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise Exception(f"LLM error: {response.status_code} - {response.text}")

    async def chat(self, messages: List[Dict], temperature: float = 0.1,
                   max_tokens: int = 4096) -> str:
        """Async chat request - runs in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._sync_chat(messages, temperature, max_tokens)
        )

    async def chat_with_vision(self, prompt: str, image_b64: str,
                               temperature: float = 0.1) -> str:
        """Async vision request"""
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}"
                    }
                }
            ]
        }]
        return await self.chat(messages, temperature)


class BaseAgent:
    """Base class for extraction agents"""

    def __init__(self, rag_engine: RAGEngine, llm: LLMClient,
                 stream_callback: Optional[Callable] = None):
        self.rag = rag_engine
        self.llm = llm
        self.stream_callback = stream_callback
        self.name = self.__class__.__name__

    def stream(self, message: str, progress: float = 0.0, data: Dict = None):
        """Send streaming message"""
        if self.stream_callback:
            self.stream_callback(StreamMessage(
                agent=self.name,
                message=message,
                progress=progress,
                data=data
            ))

    def extract_json(self, text: str) -> Dict:
        """Extract JSON from LLM response"""
        try:
            # Try to find JSON in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        return {}

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        """Run extraction - to be implemented by subclasses"""
        raise NotImplementedError


class ProjectInfoAgent(BaseAgent):
    """Extract core project information"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for project information...")

        # Query for project info
        results = self.rag.query(
            project_name,
            "project name architect owner address location city state zip",
            n_results=10,
            doc_types=["specs", "other"]
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error="No project information found"
            )

        self.stream("Extracting project details...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:5]])
        prompt = f"""Extract project information from these documents. Return JSON only:

{context}

Return this exact JSON structure (use null for missing values):
{{
    "name": "project name",
    "number": "project number or null",
    "architect": "architect firm name or null",
    "owner": "owner/client name or null",
    "location": {{
        "address": "street address or null",
        "city": "city or null",
        "state": "state or null",
        "zip": "zip code or null"
    }}
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)

            self.stream("Project info extracted", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"project": data}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class ScheduleInfoAgent(BaseAgent):
    """Extract project schedule and timeline"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for schedule information...")

        results = self.rag.query(
            project_name,
            "bid date pre-bid meeting substantial completion final completion project duration liquidated damages calendar days",
            n_results=10,
            doc_types=["specs", "other"]
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error="No schedule information found"
            )

        self.stream("Extracting schedule details...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:5]])
        prompt = f"""Extract project schedule information from these documents. Return JSON only:

{context}

Return this exact JSON structure (use null for missing values):
{{
    "bid_date": "YYYY-MM-DD or null",
    "pre_bid_meeting": {{
        "date": "date and time or null",
        "location": "location or null",
        "mandatory": true/false or null
    }},
    "project_duration": "e.g., '180 calendar days' or null",
    "substantial_completion": "date or duration description or null",
    "final_completion": "date or duration description or null",
    "liquidated_damages": "e.g., '$500 per day' or null"
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)

            self.stream("Schedule info extracted", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"schedule": data}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class BidRequirementsAgent(BaseAgent):
    """Extract bidding requirements and conditions"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for bid requirements...")

        results = self.rag.query(
            project_name,
            "DCAM prevailing wage filed sub-bid prequalification bonding MBE WBE DBE certified insurance bidder requirements",
            n_results=15,
            doc_types=["specs", "other"]
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error="No bid requirements found"
            )

        self.stream("Extracting bid requirements...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:7]])
        prompt = f"""Extract bidding requirements from these documents. Return JSON only:

{context}

Return this exact JSON structure:
{{
    "dcam_required": true/false,
    "prevailing_wage": true/false,
    "prequalification_required": true/false,
    "filed_sub_bids": ["list of trades requiring filed sub-bids"],
    "mbe_goal_percent": number or null,
    "wbe_goal_percent": number or null,
    "dbe_goal_percent": number or null,
    "bonding": "bonding requirements description or null",
    "insurance": "insurance requirements description or null",
    "other_conditions": ["list of other special conditions"]
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)

            self.stream("Bid requirements extracted", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"bid_requirements": data}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class Division8ScopeAgent(BaseAgent):
    """Extract Division 8 scope and specification sections"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for Division 8 specifications...")

        # Search for each major Division 8 area
        scope_queries = [
            "08 Division 8 openings scope",
            "08 11 metal doors frames hollow",
            "08 14 wood doors architectural",
            "08 41 storefront entrance aluminum",
            "08 44 curtain wall glazed",
            "08 50 08 51 windows aluminum vinyl",
            "08 71 door hardware lockset",
            "08 80 08 81 glazing glass insulating"
        ]

        all_results = []
        for query in scope_queries:
            results = self.rag.query(project_name, query, n_results=5)
            all_results.extend(results)

        if not all_results:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error="No Division 8 content found"
            )

        self.stream("Extracting Division 8 scope...", 0.5)

        # Deduplicate
        seen = set()
        unique_results = []
        for r in all_results:
            key = r["content"][:200]
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        context = "\n---\n".join([r["content"] for r in unique_results[:10]])
        prompt = f"""Analyze these Division 8 (Openings) specification excerpts. Return JSON only:

{context}

Return this exact JSON structure:
{{
    "spec_sections": [
        {{"number": "08 11 13", "title": "Hollow Metal Doors and Frames", "in_scope": true}},
        ...list all Division 8 sections found
    ],
    "scope_summary": "Brief summary of Division 8 scope for this project",
    "windows": {{
        "in_scope": true/false,
        "manufacturers": ["list of specified/approved manufacturers"],
        "products": ["list of product names/series"],
        "types": [
            {{"type": "Fixed", "material": "Aluminum", "spec_section": "08 51 13"}}
        ],
        "notes": "any special notes"
    }},
    "storefront": {{
        "in_scope": true/false,
        "manufacturers": ["list"],
        "products": ["list"],
        "notes": "any notes"
    }},
    "curtain_wall": {{
        "in_scope": true/false,
        "manufacturers": ["list"],
        "products": ["list"],
        "notes": "any notes"
    }},
    "doors": {{
        "in_scope": true/false,
        "types": [
            {{"type": "Hollow Metal", "material": "Steel", "fire_rated": true}}
        ],
        "notes": "any notes"
    }},
    "hardware": {{
        "in_scope": true/false,
        "manufacturers": ["list"],
        "keying_system": "description or null",
        "notes": "any notes"
    }},
    "glazing": {{
        "in_scope": true/false,
        "types": ["Insulated", "Tempered", "Laminated", etc.],
        "performance": {{
            "u_value": number or null,
            "shgc": number or null,
            "vlt": number or null,
            "stc": number or null
        }},
        "notes": "any notes"
    }}
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)

            self.stream("Division 8 scope extracted", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"division_8": data}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class ScheduleVisionAgent(BaseAgent):
    """Extract door/window schedules using vision"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for schedule documents...")

        # Find schedule PDFs
        processor = DocumentProcessor()
        schedule_files = []
        for pdf in project_path.rglob("*.pdf"):
            if any(kw in pdf.name.lower() for kw in ["schedule", "door", "window", "hardware"]):
                schedule_files.append(pdf)

        if not schedule_files:
            # Fall back to RAG search
            return await self._extract_from_rag(project_name)

        self.stream(f"Found {len(schedule_files)} schedule files, extracting...", 0.3)

        all_schedules = {"windows": [], "doors": [], "storefronts": []}

        for pdf_file in schedule_files[:3]:  # Limit to first 3
            try:
                images = processor.extract_pdf_images(pdf_file, dpi=150)
                for page_num, img_b64 in images[:5]:  # Limit pages
                    self.stream(f"Analyzing {pdf_file.name} page {page_num}...", 0.5)

                    prompt = """Analyze this schedule drawing. Extract any door, window, or storefront schedules visible.

Return JSON only with this structure:
{
    "windows": [
        {"mark": "W1", "qty": 5, "width": "3'-0\"", "height": "4'-0\"", "type": "Fixed", "notes": "any notes"}
    ],
    "doors": [
        {"mark": "101", "qty": 1, "width": "3'-0\"", "height": "7'-0\"", "material": "HM", "fire_rating": "90 min", "hardware_set": "1"}
    ],
    "storefronts": [
        {"mark": "SF-1", "width": "10'-0\"", "height": "12'-0\"", "system": "Kawneer 451T"}
    ]
}

If no schedules are visible, return empty arrays. Only include rows you can clearly read."""

                    response = await self.llm.chat_with_vision(prompt, img_b64)
                    data = self.extract_json(response)

                    for key in ["windows", "doors", "storefronts"]:
                        if key in data and isinstance(data[key], list):
                            all_schedules[key].extend(data[key])

            except Exception as e:
                self.stream(f"Error processing {pdf_file.name}: {e}", 0.5)

        self.stream("Schedules extracted", 1.0, all_schedules)
        return ExtractionResult(
            agent_name=self.name,
            success=True,
            data={"openings_schedule": all_schedules}
        )

    async def _extract_from_rag(self, project_name: str) -> ExtractionResult:
        """Fall back to RAG-based extraction"""
        results = self.rag.query(
            project_name,
            "door schedule window schedule hardware set mark width height",
            n_results=10
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"openings_schedule": {"windows": [], "doors": [], "storefronts": []}}
            )

        context = "\n---\n".join([r["content"] for r in results[:5]])
        prompt = f"""Extract door and window schedule data from this text:

{context}

Return JSON with:
{{
    "windows": [{{"mark": "...", "qty": ..., "width": "...", "height": "...", "type": "...", "notes": "..."}}],
    "doors": [{{"mark": "...", "qty": ..., "width": "...", "height": "...", "material": "...", "fire_rating": "...", "hardware_set": "..."}}],
    "storefronts": [{{"mark": "...", "width": "...", "height": "...", "system": "..."}}]
}}"""

        response = await self.llm.chat([{"role": "user", "content": prompt}])
        data = self.extract_json(response)

        return ExtractionResult(
            agent_name=self.name,
            success=True,
            data={"openings_schedule": data}
        )


class EstimateAgent(BaseAgent):
    """Extract estimate and cost data"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for estimate documents...")

        results = self.rag.query(
            project_name,
            "estimate cost pricing takeoff quantity material labor total bid amount",
            n_results=15,
            doc_types=["estimates"]
        )

        if not results:
            # No estimates found
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"estimate": {"has_estimate": False}}
            )

        self.stream("Extracting estimate data...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:7]])
        prompt = f"""Extract estimate/cost data from these documents. Return JSON only:

{context}

Return this structure:
{{
    "has_estimate": true,
    "currency": "USD",
    "division_8_total": total number or null,
    "breakdown": {{
        "windows": {{"material": number, "labor": number, "total": number}},
        "doors": {{"material": number, "labor": number, "total": number}},
        "hardware": {{"material": number, "labor": number, "total": number}},
        "storefront": {{"material": number, "labor": number, "total": number}},
        "glazing": {{"material": number, "labor": number, "total": number}}
    }},
    "bid_value": overall bid value or null,
    "notes": "any notes about the estimate"
}}

Use null for any values not found. Numbers should be numeric, not strings."""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)
            if not data:
                data = {"has_estimate": False}

            self.stream("Estimate data extracted", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"estimate": data}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class AddendumAgent(BaseAgent):
    """Extract addendum information"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for addendums...")

        results = self.rag.query(
            project_name,
            "addendum revision changes bid date extended modified specification drawing",
            n_results=15,
            doc_types=["addendums"]
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"addendums": []}
            )

        self.stream("Extracting addendum details...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:7]])
        prompt = f"""Extract addendum information from these documents. Return JSON only:

{context}

Return this structure - an array of addendums:
{{
    "addendums": [
        {{
            "number": 1,
            "date": "YYYY-MM-DD or null",
            "bid_date_changed": true/false,
            "new_bid_date": "new date if changed or null",
            "division_8_changes": {{
                "has_changes": true/false,
                "summary": "brief summary of Division 8 changes",
                "window_changes": ["list of window-related changes"],
                "door_changes": ["list of door-related changes"],
                "hardware_changes": ["list of hardware-related changes"],
                "glazing_changes": ["list of glazing-related changes"],
                "other_changes": ["other Division 8 changes"]
            }},
            "substitutions": ["list of approved substitutions"]
        }}
    ]
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)
            addendums = data.get("addendums", [])

            self.stream(f"Found {len(addendums)} addendums", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"addendums": addendums}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class RFIAgent(BaseAgent):
    """Extract RFI information"""

    async def run(self, project_name: str, project_path: Path) -> ExtractionResult:
        self.stream("Searching for RFIs...")

        results = self.rag.query(
            project_name,
            "RFI request for information question response clarification Division 8 door window hardware glazing",
            n_results=15,
            doc_types=["rfis"]
        )

        if not results:
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"rfis": []}
            )

        self.stream("Extracting RFI details...", 0.5)

        context = "\n---\n".join([r["content"] for r in results[:7]])
        prompt = f"""Extract RFI (Request for Information) data from these documents. Only include RFIs related to Division 8 (doors, windows, hardware, glazing, storefront, curtain wall). Return JSON only:

{context}

Return this structure:
{{
    "rfis": [
        {{
            "number": "RFI-001",
            "date": "date or null",
            "subject": "brief subject",
            "category": "windows|doors|hardware|glazing|storefront|curtain_wall|general|other",
            "question": "the question asked",
            "response": "the response or null if pending",
            "scope_impact": "description of scope impact or null",
            "status": "open|closed|pending"
        }}
    ]
}}"""

        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            data = self.extract_json(response)
            rfis = data.get("rfis", [])

            self.stream(f"Found {len(rfis)} relevant RFIs", 1.0, data)
            return ExtractionResult(
                agent_name=self.name,
                success=True,
                data={"rfis": rfis}
            )
        except Exception as e:
            return ExtractionResult(
                agent_name=self.name,
                success=False,
                data={},
                error=str(e)
            )


class ExtractionOrchestrator:
    """Orchestrates multiple extraction agents"""

    def __init__(self, rag_engine: RAGEngine,
                 stream_callback: Optional[Callable] = None):
        self.rag = rag_engine
        self.llm = LLMClient()
        self.stream_callback = stream_callback
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Initialize agents
        self.agents = [
            ProjectInfoAgent(rag_engine, self.llm, stream_callback),
            ScheduleInfoAgent(rag_engine, self.llm, stream_callback),
            BidRequirementsAgent(rag_engine, self.llm, stream_callback),
            Division8ScopeAgent(rag_engine, self.llm, stream_callback),
            ScheduleVisionAgent(rag_engine, self.llm, stream_callback),
            EstimateAgent(rag_engine, self.llm, stream_callback),
            AddendumAgent(rag_engine, self.llm, stream_callback),
            RFIAgent(rag_engine, self.llm, stream_callback),
        ]

    async def extract_project(self, project_path: Path) -> Dict:
        """Run all extraction agents on a project"""
        project_name = project_path.name

        # Create base result structure
        result = {
            "meta": {
                "schema_version": "1.0.0",
                "extracted_at": datetime.now().isoformat(),
                "extractor_model": LLM_MODEL,
                "source_folder": str(project_path)
            },
            "project": {},
            "schedule": {},
            "bid_requirements": {},
            "division_8": {},
            "openings_schedule": {"windows": [], "doors": [], "storefronts": []},
            "estimate": {"has_estimate": False},
            "addendums": [],
            "rfis": [],
            "documents": {}
        }

        # Index the project first (reuse existing index from pipeline when available)
        # Check disk-based index first (survives restarts), then in-memory
        has_index = self.rag.is_project_indexed(project_name)
        summary = self.rag.get_project_summary(project_name) if has_index else {}

        if not has_index:
            if self.stream_callback:
                self.stream_callback(StreamMessage(
                    agent="Indexer",
                    message=f"Indexing {project_name}...",
                    progress=0.0
                ))

            def index_progress(msg, current, total):
                if self.stream_callback:
                    self.stream_callback(StreamMessage(
                        agent="Indexer",
                        message=msg,
                        progress=current / total if total > 0 else 0
                    ))

            # Run indexing in thread pool to not block event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: self.rag.index_project(project_path, index_progress)
            )

            summary = self.rag.get_project_summary(project_name)
        else:
            if self.stream_callback:
                self.stream_callback(StreamMessage(
                    agent="Indexer",
                    message=f"Using existing index for {project_name}",
                    progress=1.0
                ))

        # Get document summary
        result["documents"] = {
            "specs": [],
            "drawings": [],
            "schedules": [],
            "addendums": [],
            "estimates": [],
            "rfis": [],
            "other": []
        }

        for doc_path, doc_info in summary.get("file_manifest", {}).items():
            doc_type = doc_info.get("type", "other")
            if doc_type in result["documents"]:
                result["documents"][doc_type].append(doc_path)
            else:
                result["documents"]["other"].append(doc_path)

        # Run agents in parallel
        if self.stream_callback:
            self.stream_callback(StreamMessage(
                agent="Orchestrator",
                message=f"Running {len(self.agents)} extraction agents...",
                progress=0.0
            ))

        tasks = [agent.run(project_name, project_path) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        for i, agent_result in enumerate(results):
            if isinstance(agent_result, Exception):
                if self.stream_callback:
                    self.stream_callback(StreamMessage(
                        agent=self.agents[i].name,
                        message=f"Error: {agent_result}",
                        progress=1.0
                    ))
                continue

            if agent_result.success and agent_result.data:
                result.update(agent_result.data)

        # Enrich with CSI Masterformat data
        if CSI_AVAILABLE:
            if self.stream_callback:
                self.stream_callback(StreamMessage(
                    agent="CSIEnricher",
                    message="Enriching with CSI Masterformat data...",
                    progress=0.5
                ))
            result = self._enrich_with_csi(result)

        if self.stream_callback:
            self.stream_callback(StreamMessage(
                agent="Orchestrator",
                message="Extraction complete!",
                progress=1.0,
                is_complete=True
            ))

        return result

    def _enrich_with_csi(self, result: Dict) -> Dict:
        """Enrich extraction results with CSI Masterformat data."""
        if not CSI_AVAILABLE:
            return result

        try:
            csi_service = CSIService()

            # Enrich Division 8 spec sections
            if "division_8" in result and "spec_sections" in result["division_8"]:
                enriched_sections = []
                for section in result["division_8"]["spec_sections"]:
                    section_num = section.get("number", "")
                    if section_num:
                        info = get_section_info(section_num)
                        section["csi_title"] = info.get("title", section.get("title", ""))
                        section["csi_division_title"] = info.get("division_title", "")
                        section["category"] = categorize_section(section_num)
                    enriched_sections.append(section)
                result["division_8"]["spec_sections"] = enriched_sections

            # Extract additional CSI sections from scope text
            scope_text = ""
            if "division_8" in result:
                div8 = result["division_8"]
                scope_text += str(div8.get("scope_summary", "")) + " "
                for key in ["windows", "storefront", "curtain_wall", "doors", "hardware", "glazing"]:
                    if key in div8:
                        scope_text += str(div8[key]) + " "

            # Find additional CSI sections mentioned in text
            if scope_text:
                detected_sections = extract_section_references(scope_text)
                existing_nums = {s.get("number", "") for s in result.get("division_8", {}).get("spec_sections", [])}

                for section_id in detected_sections:
                    if section_id not in existing_nums:
                        info = get_section_info(section_id)
                        result.setdefault("division_8", {}).setdefault("spec_sections", []).append({
                            "number": section_id,
                            "title": info.get("title", "Unknown"),
                            "csi_title": info.get("title", ""),
                            "csi_division_title": info.get("division_title", ""),
                            "category": categorize_section(section_id),
                            "in_scope": True,
                            "detected_by": "csi_enricher"
                        })

            # Detect manufacturers
            manufacturers_found = match_manufacturers(scope_text)
            if manufacturers_found:
                result.setdefault("csi_enrichment", {})["detected_manufacturers"] = [
                    {
                        "name": m["name"],
                        "product_count": m.get("product_count", 0),
                        "categories": m.get("categories", [])
                    }
                    for m in manufacturers_found
                ]

            # Add CSI enrichment metadata
            result.setdefault("csi_enrichment", {}).update({
                "enriched": True,
                "sections_detected": len(result.get("division_8", {}).get("spec_sections", [])),
                "manufacturers_detected": len(manufacturers_found) if manufacturers_found else 0
            })

        except Exception as e:
            result.setdefault("csi_enrichment", {})["error"] = str(e)

        return result
