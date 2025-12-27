"""
Division 8 RAG System with OpenRouter Generation

Uses:
- Ollama nomic-embed-text for FAST local embeddings (free, no rate limits)
- OpenRouter with free Llama 3.3 70B for generation (no OpenAI needed)

This module creates a cleaner JSON output structure optimized for
displaying in visual HTML cards.
"""

import os
import json
import hashlib
import requests
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging
from datetime import datetime

# PDF and Word parsing
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# ChromaDB for vector storage
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Local embeddings
from .ollama_embeddings import OllamaEmbedder, check_ollama_available

logger = logging.getLogger(__name__)


# OpenRouter Configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"  # Free 131K context
OPENROUTER_FALLBACK = "deepseek/deepseek-chat"  # Cheap fallback


@dataclass
class Chunk:
    """A document chunk with metadata"""
    text: str
    source_file: str
    page_num: int
    chunk_id: str
    chunk_type: str  # 'spec', 'drawing', 'schedule', 'bid_invite', 'other'


# New cleaner Division 8 JSON Schema for visual display
DIVISION_8_ANALYSIS_SCHEMA = {
    "metadata": {
        "project_id": "",
        "project_name": "",
        "analyzed_at": "",
        "embedder": "ollama-nomic-embed-text",
        "generator": OPENROUTER_MODEL,
        "chunks_analyzed": 0,
        "confidence": "medium"
    },
    "summary": {
        "scope_description": "",
        "key_items": [],
        "total_doors": 0,
        "total_windows": 0,
        "has_storefront": False,
        "has_curtain_wall": False,
        "has_hardware": True
    },
    "doors": {
        "metal_doors_frames": {
            "specified": False,
            "count": "not specified",
            "types": [],
            "manufacturers": [],
            "spec_sections": [],
            "notes": []
        },
        "wood_doors": {
            "excluded": True,
            "exclusion_note": "Division 6 - by others"
        },
        "aluminum_doors": {
            "specified": False,
            "count": "not specified",
            "types": [],
            "manufacturers": [],
            "spec_sections": [],
            "notes": []
        },
        "access_doors": {
            "specified": False,
            "count": "not specified",
            "types": [],
            "spec_sections": [],
            "notes": []
        },
        "automatic_entrances": {
            "specified": False,
            "types": [],
            "manufacturers": [],
            "spec_sections": [],
            "notes": []
        }
    },
    "windows": {
        "aluminum_windows": {
            "specified": False,
            "count": "not specified",
            "types": [],
            "manufacturers": [],
            "performance": {},
            "spec_sections": [],
            "notes": []
        },
        "vinyl_windows": {
            "specified": False,
            "count": "not specified",
            "types": [],
            "manufacturers": [],
            "performance": {},
            "spec_sections": [],
            "notes": []
        }
    },
    "storefronts": {
        "specified": False,
        "sf_estimate": 0,
        "systems": [],
        "manufacturers": [],
        "finish": "",
        "spec_sections": [],
        "notes": []
    },
    "curtain_wall": {
        "specified": False,
        "sf_estimate": 0,
        "systems": [],
        "manufacturers": [],
        "spec_sections": [],
        "notes": []
    },
    "hardware": {
        "specified": False,
        "hardware_sets": [],
        "manufacturers": [],
        "lockset_types": [],
        "finish": "",
        "access_control": False,
        "spec_sections": [],
        "notes": []
    },
    "glazing": {
        "specified": False,
        "glass_types": [],
        "performance": {},
        "spec_sections": [],
        "notes": []
    },
    "exclusions": [],
    "alternates": [],
    "clarifications_needed": [],
    "source_documents": []
}


SYSTEM_PROMPT = """You are an expert Division 8 (Openings) construction estimator. Your job is to extract Division 8 scope information from construction documents and output it in a specific JSON format.

Division 8 includes:
- Windows (all types: aluminum, vinyl, wood-clad)
- Metal doors and frames (hollow metal, aluminum)
- Door hardware (hinges, locksets, closers, etc.)
- Entrances and storefronts
- Curtain walls
- Glass and glazing
- Access doors and panels
- Automatic entrances

Division 8 EXCLUDES (note these but don't include in scope):
- Wood doors (Division 6)
- Overhead/rolling doors (often separate subcontractor)
- Finish hardware on wood doors

When analyzing documents:
1. Look for CSI sections 08 XXXX (08 11 00 through 08 91 00)
2. Identify window and door schedules with quantities
3. Note hardware sets and specifications
4. Identify any alternates or exclusions
5. Note manufacturers/products specified
6. Extract performance specs (U-factor, SHGC, STC ratings)

Output your analysis as JSON matching this exact schema:
{schema}

Rules:
- Use "not specified" for unknown counts, not null or empty string
- Include spec section numbers like "08 11 13" in spec_sections arrays
- Be specific about quantities when schedules are available
- List actual manufacturer names found in specs
- Include door/window types like "HM flush", "double-hung", "fixed"
- Set confidence to "high" if schedules found, "medium" if specs only, "low" if minimal info"""


class Division8RAGOpenRouter:
    """
    RAG system using OpenRouter for generation (no OpenAI/LM Studio needed).
    Uses local Ollama embeddings for speed and cost savings.
    """

    def __init__(
        self,
        project_folder: Path,
        openrouter_api_key: str = None,
        ollama_model: str = "nomic-embed-text",
        chroma_persist_dir: str = None,
        model: str = None
    ):
        self.project_folder = Path(project_folder)
        self.project_id = self.project_folder.name
        self.project_name = self.project_id  # Can be updated from project data

        # Set up OpenRouter for generation
        self.api_key = openrouter_api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OpenRouter API key required. Set OPENROUTER_API_KEY env var.")

        self.model = model or OPENROUTER_MODEL

        # Set up Ollama for embeddings
        if not check_ollama_available():
            raise RuntimeError("Ollama not running. Start with: ollama serve")
        self.embedder = OllamaEmbedder(ollama_model)

        # ChromaDB setup
        if chroma_persist_dir:
            self.chroma_dir = Path(chroma_persist_dir)
        else:
            self.chroma_dir = self.project_folder / ".chroma_openrouter"
        self.chroma_dir.mkdir(exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection_name = self._sanitize_collection_name(self.project_id)

        self.stats = {
            'chunks_created': 0,
            'chunks_embedded': 0,
            'tokens_used': 0,
            'api_calls': 0,
            'files_processed': 0,
            'files_skipped_cloud': 0
        }

    def _sanitize_collection_name(self, name: str) -> str:
        clean = ''.join(c if c.isalnum() else '_' for c in name.lower())
        clean = clean.strip('_')[:63]
        if len(clean) < 3:
            clean = clean + '_col'
        return clean

    def _is_cloud_only(self, filepath: Path) -> bool:
        """Check if file is a Dropbox cloud-only placeholder"""
        try:
            return filepath.stat().st_size == 0
        except:
            return True

    def _trigger_dropbox_download(self, filepath: Path) -> bool:
        """Trigger Dropbox to download a cloud-only file"""
        try:
            if filepath.stat().st_size > 0:
                return True
            with open(filepath, 'rb') as f:
                byte = f.read(1)
                if byte:
                    return True
            import time
            time.sleep(0.5)
            return filepath.stat().st_size > 0
        except Exception as e:
            logger.warning(f"Could not trigger download for {filepath.name}: {e}")
            return False

    def _call_openrouter(self, messages: List[Dict], temperature: float = 0.1) -> Dict:
        """Call OpenRouter API for chat completion"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://project-tracker.local",
            "X-Title": "Division 8 Analysis"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4000
        }

        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                self.stats['api_calls'] += 1
                if 'usage' in data:
                    self.stats['tokens_used'] += data['usage'].get('total_tokens', 0)
                return data
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                # Try fallback model
                if self.model != OPENROUTER_FALLBACK:
                    logger.info(f"Trying fallback model: {OPENROUTER_FALLBACK}")
                    payload["model"] = OPENROUTER_FALLBACK
                    response = requests.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=120
                    )
                    if response.status_code == 200:
                        return response.json()
                raise Exception(f"OpenRouter API error: {response.status_code}")

        except requests.exceptions.Timeout:
            logger.error("OpenRouter API timeout")
            raise
        except Exception as e:
            logger.error(f"OpenRouter call failed: {e}")
            raise

    def chunk_documents(self, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
        """Chunk all documents in the project folder"""
        chunks = []

        pdf_files = list(self.project_folder.rglob("*.pdf"))
        docx_files = [f for f in self.project_folder.rglob("*.docx") if not f.name.startswith('~$')]

        logger.info(f"[RAG-OpenRouter] Found {len(pdf_files)} PDFs and {len(docx_files)} Word docs")

        for pdf_path in pdf_files:
            if self._is_cloud_only(pdf_path):
                if not self._trigger_dropbox_download(pdf_path):
                    logger.warning(f"[RAG-OpenRouter] Skipping cloud-only: {pdf_path.name}")
                    self.stats['files_skipped_cloud'] += 1
                    continue

            pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
            if pdf_chunks:
                chunks.extend(pdf_chunks)
                self.stats['files_processed'] += 1

        for docx_path in docx_files:
            if self._is_cloud_only(docx_path):
                if not self._trigger_dropbox_download(docx_path):
                    self.stats['files_skipped_cloud'] += 1
                    continue

            docx_chunks = self._chunk_docx(docx_path, chunk_size, overlap)
            if docx_chunks:
                chunks.extend(docx_chunks)
                self.stats['files_processed'] += 1

        self.stats['chunks_created'] = len(chunks)
        logger.info(f"[RAG-OpenRouter] Created {len(chunks)} chunks from {self.stats['files_processed']} files")

        return chunks

    def selective_chunk_documents(self, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
        """
        Selectively chunk only Division 8 relevant documents.

        Indexes only:
        - Split spec book: Divisions 0, 1, and 8
        - Architectural drawings: A-*.pdf, G-*.pdf
        """
        chunks = []

        DIVISIONS_TO_INDEX = [
            ('Division-00-Procurement', 'Division 0'),
            ('Division-01-General', 'Division 1'),
            ('Division-08-Openings', 'Division 8'),
        ]

        specs_found = False
        total_spec_files = 0

        for div_folder, div_name in DIVISIONS_TO_INDEX:
            spec_locations = [
                self.project_folder / 'Specs' / div_folder,
                self.project_folder / 'Extracted-Data' / 'Organized' / 'Specs' / div_folder,
            ]

            for spec_folder in spec_locations:
                if spec_folder.exists():
                    pdf_files = list(spec_folder.glob('*.pdf'))
                    if pdf_files:
                        logger.info(f"[RAG-OpenRouter] Found {len(pdf_files)} {div_name} specs")
                        for pdf_path in pdf_files:
                            if self._is_cloud_only(pdf_path):
                                if not self._trigger_dropbox_download(pdf_path):
                                    self.stats['files_skipped_cloud'] += 1
                                    continue
                            pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
                            if pdf_chunks:
                                chunks.extend(pdf_chunks)
                                self.stats['files_processed'] += 1
                                total_spec_files += 1
                        specs_found = True
                        break

        # Check for architectural drawings
        drawing_locations = [
            self.project_folder / 'Drawings',
            self.project_folder / 'Extracted-Data' / 'Organized' / 'Drawings',
        ]

        drawings_found = False
        for drawings_folder in drawing_locations:
            if drawings_folder.exists():
                pdf_files = list(drawings_folder.glob('*.pdf'))
                arch_count = 0
                for pdf_path in pdf_files:
                    name_upper = pdf_path.stem.upper()
                    if name_upper.startswith('A') or name_upper.startswith('G'):
                        if self._is_cloud_only(pdf_path):
                            if not self._trigger_dropbox_download(pdf_path):
                                self.stats['files_skipped_cloud'] += 1
                                continue
                        pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
                        if pdf_chunks:
                            chunks.extend(pdf_chunks)
                            self.stats['files_processed'] += 1
                            arch_count += 1
                if arch_count > 0:
                    logger.info(f"[RAG-OpenRouter] Indexed {arch_count} architectural drawings")
                    drawings_found = True
                    break

        # Fallback to full document indexing if no split folders found
        if not specs_found and not drawings_found:
            logger.warning("[RAG-OpenRouter] No split documents found. Falling back to full indexing...")
            return self.chunk_documents(chunk_size, overlap)

        self.stats['chunks_created'] = len(chunks)
        logger.info(f"[RAG-OpenRouter] SELECTIVE: Created {len(chunks)} chunks")

        return chunks

    def _chunk_pdf(self, pdf_path: Path, chunk_size: int, overlap: int) -> List[Chunk]:
        chunks = []
        if not PDF_AVAILABLE:
            return chunks

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if not text.strip():
                        continue

                    chunk_type = self._classify_content(text, pdf_path.name)
                    page_chunks = self._split_text(
                        text, chunk_size, overlap,
                        source_file=pdf_path.name,
                        page_num=page_num,
                        chunk_type=chunk_type
                    )
                    chunks.extend(page_chunks)

        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}: {e}")

        return chunks

    def _chunk_docx(self, docx_path: Path, chunk_size: int, overlap: int) -> List[Chunk]:
        chunks = []
        if not DOCX_AVAILABLE:
            return chunks

        try:
            doc = Document(str(docx_path))
            full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
            chunk_type = self._classify_content(full_text, docx_path.name)

            chunks = self._split_text(
                full_text, chunk_size, overlap,
                source_file=docx_path.name,
                page_num=0,
                chunk_type=chunk_type
            )

        except Exception as e:
            logger.error(f"Error processing {docx_path.name}: {e}")

        return chunks

    def _classify_content(self, text: str, filename: str) -> str:
        text_lower = text.lower()
        name_lower = filename.lower()

        if any(x in text_lower for x in ['section 08', 'csi 08', '08 11 00', '08 14 00', '08 71 00']):
            return 'spec'
        if any(x in text_lower for x in ['door schedule', 'window schedule', 'hardware schedule']):
            return 'schedule'
        if any(x in name_lower for x in ['invite', 'itb', 'rfp', 'bid']):
            return 'bid_invite'
        if any(x in name_lower for x in ['drawing', 'plan', 'elevation', 'detail']):
            return 'drawing'
        return 'other'

    def _split_text(self, text: str, chunk_size: int, overlap: int,
                    source_file: str, page_num: int, chunk_type: str) -> List[Chunk]:
        chunks = []

        if len(text) <= chunk_size:
            chunk_id = hashlib.md5(f"{source_file}:{page_num}:0".encode()).hexdigest()[:12]
            chunks.append(Chunk(
                text=text,
                source_file=source_file,
                page_num=page_num,
                chunk_id=chunk_id,
                chunk_type=chunk_type
            ))
        else:
            start = 0
            chunk_num = 0
            while start < len(text):
                end = start + chunk_size
                chunk_text = text[start:end]

                chunk_id = hashlib.md5(f"{source_file}:{page_num}:{chunk_num}".encode()).hexdigest()[:12]
                chunks.append(Chunk(
                    text=chunk_text,
                    source_file=source_file,
                    page_num=page_num,
                    chunk_id=chunk_id,
                    chunk_type=chunk_type
                ))

                start = end - overlap
                chunk_num += 1

        return chunks

    def embed_and_store(self, chunks: List[Chunk]) -> None:
        """Embed chunks using Ollama and store in ChromaDB"""
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"project_id": self.project_id, "embedder": "ollama-nomic"}
            )
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            self.chroma_client = chromadb.Client()
            collection = self.chroma_client.get_or_create_collection(name=self.collection_name)

        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]

            texts = [c.text for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [
                {
                    "source_file": c.source_file,
                    "page_num": c.page_num,
                    "chunk_type": c.chunk_type
                }
                for c in batch
            ]

            try:
                embeddings = self.embedder.embed(texts)

                valid_data = [
                    (ids[j], embeddings[j], texts[j], metadatas[j])
                    for j in range(len(embeddings))
                    if embeddings[j]
                ]

                if valid_data:
                    collection.add(
                        ids=[d[0] for d in valid_data],
                        embeddings=[d[1] for d in valid_data],
                        documents=[d[2] for d in valid_data],
                        metadatas=[d[3] for d in valid_data]
                    )

                self.stats['chunks_embedded'] += len(valid_data)
                logger.info(f"[RAG-OpenRouter] Embedded batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")

            except Exception as e:
                logger.error(f"Error embedding batch: {e}")

    def retrieve(self, query: str, n_results: int = 20) -> List[Dict]:
        """Retrieve relevant chunks for a query"""
        try:
            collection = self.chroma_client.get_collection(self.collection_name)
        except Exception as e:
            logger.error(f"Collection not found: {e}")
            return []

        query_embedding = self.embedder.embed_query(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        formatted = []
        for i in range(len(results['ids'][0])):
            formatted.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if results.get('distances') else None
            })

        return formatted

    def generate_scope_summary(self, retrieved_chunks: List[Dict]) -> Dict:
        """Generate Division 8 scope summary using OpenRouter"""
        context_parts = []
        source_docs = set()

        for chunk in retrieved_chunks:
            source = chunk['metadata'].get('source_file', 'unknown')
            page = chunk['metadata'].get('page_num', 0)
            chunk_type = chunk['metadata'].get('chunk_type', 'other')
            context_parts.append(f"[{chunk_type.upper()}] {source} (p.{page}):\n{chunk['text']}\n")
            source_docs.add(source)

        context = "\n---\n".join(context_parts)
        system = SYSTEM_PROMPT.format(schema=json.dumps(DIVISION_8_ANALYSIS_SCHEMA, indent=2))

        user_prompt = f"""Analyze the following construction document excerpts and extract the Division 8 (Openings) scope information.

PROJECT: {self.project_name}

DOCUMENT EXCERPTS:
{context}

Based on these documents, provide a comprehensive Division 8 scope summary as JSON matching the schema exactly."""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_openrouter(messages)
            content = response['choices'][0]['message']['content']

            # Parse JSON from response (handle markdown code blocks)
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())

            # Ensure source_documents is populated
            result['source_documents'] = [
                {"filename": doc, "type": "spec" if "spec" in doc.lower() else "drawing"}
                for doc in source_docs
            ]

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {content[:500]}")
            return {"error": f"JSON parse error: {str(e)}", "raw_response": content[:500]}
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {"error": str(e)}

    def analyze_project(self, selective: bool = True) -> Dict:
        """
        Full RAG pipeline with OpenRouter generation.

        Args:
            selective: If True, only index Division 8 relevant docs (faster)
        """
        logger.info(f"[RAG-OpenRouter] Starting analysis for: {self.project_id}")

        if selective:
            chunks = self.selective_chunk_documents()
        else:
            chunks = self.chunk_documents()

        if not chunks:
            return {"error": "No documents found to analyze"}

        self.embed_and_store(chunks)

        query = "Division 8 windows doors hardware specifications schedule openings glazing storefront entrance metal frames"
        retrieved = self.retrieve(query, n_results=30)
        logger.info(f"[RAG-OpenRouter] Retrieved {len(retrieved)} relevant chunks")

        summary = self.generate_scope_summary(retrieved)

        # Add/update metadata
        if 'metadata' not in summary:
            summary['metadata'] = {}

        summary['metadata'].update({
            'project_id': self.project_id,
            'project_name': self.project_name,
            'analyzed_at': datetime.now().isoformat(),
            'embedder': 'ollama-nomic-embed-text',
            'generator': self.model,
            'chunks_analyzed': len(chunks),
            'chunks_retrieved': len(retrieved),
            'confidence': self._determine_confidence(retrieved, summary),
            'stats': self.stats
        })

        return summary

    def _determine_confidence(self, retrieved: List[Dict], summary: Dict) -> str:
        """Determine confidence level based on available data"""
        has_schedules = any(
            chunk['metadata'].get('chunk_type') == 'schedule'
            for chunk in retrieved
        )
        has_specs = any(
            chunk['metadata'].get('chunk_type') == 'spec'
            for chunk in retrieved
        )

        # Check if we found quantities
        doors = summary.get('doors', {})
        windows = summary.get('windows', {})
        has_quantities = (
            doors.get('metal_doors_frames', {}).get('count', 'not specified') != 'not specified' or
            windows.get('aluminum_windows', {}).get('count', 'not specified') != 'not specified' or
            windows.get('vinyl_windows', {}).get('count', 'not specified') != 'not specified'
        )

        if has_schedules and has_quantities:
            return 'high'
        elif has_specs:
            return 'medium'
        else:
            return 'low'

    def save_results(self, results: Dict, output_path: Path = None) -> Path:
        """Save analysis results to JSON file"""
        if output_path is None:
            output_path = self.project_folder / "division8_analysis.json"

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"[RAG-OpenRouter] Saved results to {output_path}")
        return output_path


def analyze_project_openrouter(project_folder: Path, selective: bool = True) -> Dict:
    """
    Convenience function for OpenRouter RAG analysis.

    Args:
        project_folder: Path to project folder
        selective: If True, only index Division 8 relevant docs

    Returns:
        Analysis results dict
    """
    rag = Division8RAGOpenRouter(project_folder)
    results = rag.analyze_project(selective=selective)
    rag.save_results(results)
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python3 division8_rag_openrouter.py <project_folder>")
        sys.exit(1)

    project_folder = Path(sys.argv[1])
    if not project_folder.exists():
        print(f"Error: Folder not found: {project_folder}")
        sys.exit(1)

    print(f"Analyzing Division 8 scope (OpenRouter): {project_folder.name}")
    print("="*60)

    results = analyze_project_openrouter(project_folder)
    print("\nResults:")
    print(json.dumps(results, indent=2))
