"""
Division 8 RAG System with Local Embeddings

Uses Ollama nomic-embed-text for FAST local embeddings instead of OpenAI API.
Still uses GPT for generation (fast + cheap).

Key differences from division8_rag.py:
- Embeddings: Ollama (local, no rate limits, ~10x faster)
- Generation: Still OpenAI GPT-5 nano (fast, cheap, good quality)

Also includes Dropbox cloud-only file handling.
"""

import os
import json
import hashlib
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

# OpenAI for generation only
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ChromaDB for vector storage
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Local embeddings
from .ollama_embeddings import OllamaEmbedder, check_ollama_available

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A document chunk with metadata"""
    text: str
    source_file: str
    page_num: int
    chunk_id: str
    chunk_type: str  # 'spec', 'drawing', 'schedule', 'bid_invite', 'other'


# Division 8 JSON Schema for output
DIVISION_8_SCHEMA = {
    "project_summary": {
        "name": "",
        "location": "",
        "type": "",
    },
    "windows": {
        "specified": True,
        "types": [],
        "manufacturers": [],
        "count_estimate": "",
        "performance_specs": {},
        "notes": []
    },
    "doors": {
        "metal_doors": {
            "specified": True,
            "types": [],
            "count_estimate": "",
            "notes": []
        },
        "wood_doors_excluded": {
            "present_in_project": False,
            "note": ""
        },
        "entrance_doors": {
            "specified": False,
            "types": [],
            "notes": []
        }
    },
    "hardware": {
        "specified": True,
        "manufacturers": [],
        "lockset_types": [],
        "finish": "",
        "notes": []
    },
    "glazing_systems": {
        "storefront": {
            "specified": False,
            "manufacturers": [],
            "notes": []
        },
        "curtain_wall": {
            "specified": False,
            "manufacturers": [],
            "notes": []
        }
    },
    "exclusions": [],
    "alternates": [],
    "special_requirements": []
}


SYSTEM_PROMPT = """You are an expert Division 8 (Openings) construction estimator. Your job is to extract Division 8 scope information from construction documents.

Division 8 includes:
- Windows (all types)
- Metal doors and frames (hollow metal, aluminum)
- Door hardware (hinges, locksets, closers, etc.)
- Entrances and storefronts
- Curtain walls
- Glass and glazing

Division 8 EXCLUDES (note these but don't include in scope):
- Wood doors (Division 6)
- Overhead/rolling doors (Division 8 but often separate subcontractor)
- Finish hardware on wood doors

When analyzing documents:
1. Look for CSI sections 08 XXXX
2. Identify window and door schedules
3. Note hardware sets and specifications
4. Identify any alternates or exclusions
5. Note manufacturers/products specified

Output your analysis as JSON matching this schema:
{schema}

Be specific about quantities when schedules are available. If information is not found, use null or empty arrays."""


def trigger_dropbox_download(filepath: Path) -> bool:
    """
    Trigger Dropbox to download a cloud-only file by reading it.

    Dropbox creates placeholder files (size 0) for cloud-only content.
    Attempting to read the file triggers the download.

    Returns True if file is now available, False if still placeholder.
    """
    try:
        # Check current size
        if filepath.stat().st_size > 0:
            return True  # Already downloaded

        # Try to read first byte - this triggers Dropbox download
        with open(filepath, 'rb') as f:
            byte = f.read(1)
            if byte:
                return True

        # Wait a moment and check again
        import time
        time.sleep(0.5)

        return filepath.stat().st_size > 0

    except Exception as e:
        logger.warning(f"Could not trigger download for {filepath.name}: {e}")
        return False


class Division8RAGLocal:
    """
    RAG system using local Ollama embeddings for speed.
    """

    def __init__(
        self,
        project_folder: Path,
        openai_api_key: str = None,
        ollama_model: str = "nomic-embed-text",
        chroma_persist_dir: str = None
    ):
        self.project_folder = Path(project_folder)
        self.project_id = self.project_folder.name

        # Set up OpenAI for generation
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required for generation")
        self.openai_client = OpenAI(api_key=self.api_key)

        # Set up Ollama for embeddings
        if not check_ollama_available():
            raise RuntimeError("Ollama not running. Start with: ollama serve")
        self.embedder = OllamaEmbedder(ollama_model)

        # ChromaDB setup
        if chroma_persist_dir:
            self.chroma_dir = Path(chroma_persist_dir)
        else:
            self.chroma_dir = self.project_folder / ".chroma_local"
        self.chroma_dir.mkdir(exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection_name = self._sanitize_collection_name(self.project_id)

        self.stats = {
            'chunks_created': 0,
            'chunks_embedded': 0,
            'tokens_generated': 0,
            'api_calls': 0,
            'files_processed': 0,
            'files_skipped_cloud': 0
        }

        # Parse email metadata if available
        self.email_metadata = self._parse_email_metadata()

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

    def _parse_email_metadata(self) -> Optional[Dict]:
        """Parse email file if present in project folder"""
        try:
            # Look for .eml files in project folder
            eml_files = list(self.project_folder.glob("*.eml"))
            if not eml_files:
                return None

            # Import email parser
            from modules.intake.email_parser import EmailParser

            # Parse the first email found
            parser = EmailParser(llm_provider='auto')
            email_data = parser.parse_eml(eml_files[0])

            logger.info(f"[RAG-Local] Parsed email: {eml_files[0].name}")
            return email_data

        except Exception as e:
            logger.warning(f"[RAG-Local] Could not parse email: {e}")
            return None

    def chunk_documents(self, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
        """Chunk all documents in the project folder"""
        chunks = []

        pdf_files = list(self.project_folder.rglob("*.pdf"))
        docx_files = [f for f in self.project_folder.rglob("*.docx") if not f.name.startswith('~$')]

        logger.info(f"[RAG-Local] Found {len(pdf_files)} PDFs and {len(docx_files)} Word docs")

        # Process PDFs
        for pdf_path in pdf_files:
            # Check for cloud-only files
            if self._is_cloud_only(pdf_path):
                # Try to trigger download
                if not trigger_dropbox_download(pdf_path):
                    logger.warning(f"[RAG-Local] Skipping cloud-only: {pdf_path.name}")
                    self.stats['files_skipped_cloud'] += 1
                    continue

            pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
            if pdf_chunks:
                chunks.extend(pdf_chunks)
                self.stats['files_processed'] += 1

        # Process Word docs
        for docx_path in docx_files:
            if self._is_cloud_only(docx_path):
                if not trigger_dropbox_download(docx_path):
                    logger.warning(f"[RAG-Local] Skipping cloud-only: {docx_path.name}")
                    self.stats['files_skipped_cloud'] += 1
                    continue

            docx_chunks = self._chunk_docx(docx_path, chunk_size, overlap)
            if docx_chunks:
                chunks.extend(docx_chunks)
                self.stats['files_processed'] += 1

        self.stats['chunks_created'] = len(chunks)
        logger.info(f"[RAG-Local] Created {len(chunks)} chunks from {self.stats['files_processed']} files")

        if self.stats['files_skipped_cloud'] > 0:
            logger.warning(f"[RAG-Local] Skipped {self.stats['files_skipped_cloud']} cloud-only files")

        return chunks

    def selective_chunk_documents(self, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
        """
        Selectively chunk only Division 8 relevant documents.

        Indexes only:
        - Split spec book: Divisions 0, 1, and 8 (bidding, general requirements, openings)
        - Architectural drawings: Drawings/A-*.pdf, Drawings/G-*.pdf (cover sheets)
        - Also checks for alternate locations: Extracted-Data/Organized/

        This dramatically reduces indexing time and improves retrieval relevance.
        """
        chunks = []

        # Divisions to index from specs (0=procurement, 1=general, 8=openings)
        DIVISIONS_TO_INDEX = [
            ('Division-00-Procurement', 'Division 0'),
            ('Division-01-General', 'Division 1'),
            ('Division-08-Openings', 'Division 8'),
        ]

        # Check for split spec book (Divisions 0, 1, 8)
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
                        logger.info(f"[RAG-Local] Found {len(pdf_files)} {div_name} specs in {spec_folder}")
                        for pdf_path in pdf_files:
                            if self._is_cloud_only(pdf_path):
                                if not trigger_dropbox_download(pdf_path):
                                    self.stats['files_skipped_cloud'] += 1
                                    continue
                            pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
                            if pdf_chunks:
                                chunks.extend(pdf_chunks)
                                self.stats['files_processed'] += 1
                                total_spec_files += 1
                        specs_found = True
                        break  # Found this division, move to next

        if specs_found:
            logger.info(f"[RAG-Local] Indexed {total_spec_files} spec files from Divisions 0, 1, 8")

        # Check for split drawings (Architectural only: A-*, G-*)
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
                    # Only architectural (A-*) and general/cover (G-*) sheets
                    if name_upper.startswith('A') or name_upper.startswith('G') or name_upper.startswith('A-') or name_upper.startswith('G-'):
                        if self._is_cloud_only(pdf_path):
                            if not trigger_dropbox_download(pdf_path):
                                self.stats['files_skipped_cloud'] += 1
                                continue
                        pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
                        if pdf_chunks:
                            chunks.extend(pdf_chunks)
                            self.stats['files_processed'] += 1
                            arch_count += 1
                if arch_count > 0:
                    logger.info(f"[RAG-Local] Indexed {arch_count} architectural drawings from {drawings_folder}")
                    drawings_found = True
                    break

        # If no split folders found, log warning and fall back to regular chunking
        if not specs_found and not drawings_found:
            logger.warning(f"[RAG-Local] No split documents found. Consider running split_specs and split_drawings first.")
            logger.info(f"[RAG-Local] Falling back to full document indexing...")
            return self.chunk_documents(chunk_size, overlap)

        self.stats['chunks_created'] = len(chunks)
        logger.info(f"[RAG-Local] SELECTIVE: Created {len(chunks)} chunks from {self.stats['files_processed']} files (specs: {specs_found}, drawings: {drawings_found})")

        return chunks

    def analyze_project_selective(self) -> Dict:
        """
        Full RAG pipeline using selective document indexing.

        Only indexes Division 8 specs and architectural drawings for faster,
        more relevant analysis.
        """
        logger.info(f"[RAG-Local] Starting SELECTIVE analysis for: {self.project_id}")

        chunks = self.selective_chunk_documents()
        if not chunks:
            return {"error": "No documents found to analyze"}

        self.embed_and_store(chunks)

        query = "Division 8 windows doors hardware specifications schedule openings glazing storefront entrance"
        retrieved = self.retrieve(query, n_results=30)
        logger.info(f"[RAG-Local] Retrieved {len(retrieved)} relevant chunks")

        summary = self.generate_scope_summary(retrieved)

        # Include email metadata if available
        if self.email_metadata:
            summary['email_metadata'] = self.email_metadata

        summary['_rag_metadata'] = {
            'project_id': self.project_id,
            'embedder': 'ollama-nomic-embed-text',
            'generator': 'gpt-5-nano',
            'chunks_analyzed': len(chunks),
            'chunks_retrieved': len(retrieved),
            'analyzed_at': datetime.now().isoformat(),
            'indexing_mode': 'selective',
            'stats': self.stats,
            'email_parsed': self.email_metadata is not None
        }

        return summary

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

        # Embed in batches (local is fast but batch for efficiency)
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
                # Get embeddings from Ollama (LOCAL - FAST!)
                embeddings = self.embedder.embed(texts)

                # Filter out any empty embeddings
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
                logger.info(f"[RAG-Local] Embedded batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")

            except Exception as e:
                logger.error(f"Error embedding batch: {e}")

    def retrieve(self, query: str, n_results: int = 20) -> List[Dict]:
        """Retrieve relevant chunks for a query"""
        try:
            collection = self.chroma_client.get_collection(self.collection_name)
        except Exception as e:
            logger.error(f"Collection not found: {e}")
            return []

        # Embed query using Ollama
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
        """Generate Division 8 scope summary using OpenAI"""
        context_parts = []
        for chunk in retrieved_chunks:
            source = chunk['metadata'].get('source_file', 'unknown')
            page = chunk['metadata'].get('page_num', 0)
            chunk_type = chunk['metadata'].get('chunk_type', 'other')
            context_parts.append(f"[{chunk_type.upper()}] {source} (p.{page}):\n{chunk['text']}\n")

        context = "\n---\n".join(context_parts)
        system = SYSTEM_PROMPT.format(schema=json.dumps(DIVISION_8_SCHEMA, indent=2))

        user_prompt = f"""Analyze the following construction document excerpts and extract the Division 8 (Openings) scope information.

DOCUMENT EXCERPTS:
{context}

Based on these documents, provide a comprehensive Division 8 scope summary as JSON."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            self.stats['api_calls'] += 1
            self.stats['tokens_generated'] += response.usage.total_tokens

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {"error": str(e)}

    def analyze_project(self) -> Dict:
        """Full RAG pipeline with local embeddings"""
        logger.info(f"[RAG-Local] Starting analysis for: {self.project_id}")

        chunks = self.chunk_documents()
        if not chunks:
            return {"error": "No documents found to analyze"}

        self.embed_and_store(chunks)

        query = "Division 8 windows doors hardware specifications schedule openings glazing storefront entrance"
        retrieved = self.retrieve(query, n_results=30)
        logger.info(f"[RAG-Local] Retrieved {len(retrieved)} relevant chunks")

        summary = self.generate_scope_summary(retrieved)

        # Include email metadata if available
        if self.email_metadata:
            summary['email_metadata'] = self.email_metadata

        summary['_rag_metadata'] = {
            'project_id': self.project_id,
            'embedder': 'ollama-nomic-embed-text',
            'generator': 'gpt-5-nano',
            'chunks_analyzed': len(chunks),
            'chunks_retrieved': len(retrieved),
            'analyzed_at': datetime.now().isoformat(),
            'stats': self.stats,
            'email_parsed': self.email_metadata is not None
        }

        return summary

    def save_results(self, results: Dict, output_path: Path = None) -> Path:
        """Save analysis results to database and JSON file"""
        if output_path is None:
            output_path = self.project_folder / "division8_rag_analysis.json"

        # Add scope_summary at top level for easier access
        if 'scope_summary' not in results and results.get('project_summary'):
            results['scope_summary'] = self._build_scope_summary(results)

        # Add analyzed_at at top level
        if '_rag_metadata' in results and 'analyzed_at' in results['_rag_metadata']:
            results['analyzed_at'] = results['_rag_metadata']['analyzed_at']

        # Save to database first
        self._save_to_database(results)

        # Also save to JSON for backward compatibility
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"[RAG-Local] Saved results to {output_path}")
        return output_path

    def _save_to_database(self, results: Dict) -> None:
        """Save Division 8 scope analysis to database"""
        try:
            from modules.database import queries

            # Extract data from results
            windows = results.get('windows', {})
            doors = results.get('doors', {})
            hardware = results.get('hardware', {})
            glazing = results.get('glazing_systems', {})
            metadata = results.get('_rag_metadata', {})

            # Parse generated_at timestamp
            generated_at = None
            if metadata.get('analyzed_at'):
                try:
                    generated_at = datetime.fromisoformat(metadata['analyzed_at'])
                except:
                    pass

            # Build scope data for database
            scope_data = {
                'scope_summary': results.get('scope_summary'),
                'confidence': 'high' if metadata.get('chunks_retrieved', 0) > 20 else 'medium',

                # Windows
                'windows_count': windows.get('count_estimate'),
                'windows_types': windows.get('types', []),
                'windows_notes': '\n'.join(windows.get('notes', [])) if windows.get('notes') else None,

                # Doors
                'metal_door_count': doors.get('metal_doors', {}).get('count_estimate'),
                'wood_door_count': str(doors.get('wood_doors_excluded', {}).get('present_in_project', False)),
                'doors_notes': '\n'.join(doors.get('metal_doors', {}).get('notes', [])) if doors.get('metal_doors', {}).get('notes') else None,

                # Storefront
                'storefront_description': str(glazing.get('storefront', {}).get('manufacturers', [])) if glazing.get('storefront', {}).get('specified') else None,
                'storefront_sf_estimate': None,  # Not in current schema

                # Hardware
                'hardware_groups': None,  # Not in current schema
                'hardware_manufacturers': hardware.get('manufacturers', []),
                'hardware_notes': '\n'.join(hardware.get('notes', [])) if hardware.get('notes') else None,

                # Glass
                'glass_specs': None,  # Not in current schema
                'glass_notes': None,

                # Exclusions
                'exclusions': results.get('exclusions', []),

                # RAG metadata
                'embedder_model': metadata.get('embedder', 'ollama-nomic-embed-text'),
                'generator_model': metadata.get('generator', 'gpt-5-nano'),
                'chunks_analyzed': metadata.get('chunks_analyzed'),
                'total_chunks': metadata.get('chunks_analyzed'),
                'tokens_used': metadata.get('stats', {}).get('tokens_generated'),
                'generated_at': generated_at
            }

            # Save to database
            queries.save_division8_scope(self.project_id, scope_data)
            logger.info(f"[RAG-Local] Saved Division 8 scope to database for project {self.project_id}")

        except ImportError:
            logger.warning("[RAG-Local] Database module not available, only saving to JSON")
        except Exception as e:
            logger.error(f"[RAG-Local] Failed to save to database: {e}")
            # Continue - JSON fallback will still work

    def _build_scope_summary(self, results: Dict) -> str:
        """Build a text summary from structured results"""
        parts = []

        proj = results.get('project_summary', {})
        if proj.get('name'):
            parts.append(f"Project: {proj['name']}")

        windows = results.get('windows', {})
        if windows.get('specified'):
            count = windows.get('count_estimate', 'unknown')
            types = ', '.join(windows.get('types', [])) or 'various'
            parts.append(f"Windows: {count} ({types})")

        doors = results.get('doors', {})
        metal = doors.get('metal_doors', {})
        if metal.get('specified'):
            count = metal.get('count_estimate', 'unknown')
            parts.append(f"Metal Doors: {count}")

        wood_excl = doors.get('wood_doors_excluded', {})
        if wood_excl.get('present_in_project'):
            parts.append(f"Wood Doors: EXCLUDED - {wood_excl.get('note', 'by others')}")

        glazing = results.get('glazing_systems', {})
        if glazing.get('storefront', {}).get('specified'):
            parts.append("Storefront: Yes")
        if glazing.get('curtain_wall', {}).get('specified'):
            parts.append("Curtain Wall: Yes")

        return "; ".join(parts) if parts else "Division 8 scope analysis complete"


def analyze_project_local(project_folder: Path, openai_api_key: str = None) -> Dict:
    """Convenience function for local RAG analysis"""
    rag = Division8RAGLocal(project_folder, openai_api_key)
    results = rag.analyze_project()
    rag.save_results(results)
    return results


def analyze_project_selective(project_folder: Path, openai_api_key: str = None) -> Dict:
    """
    Convenience function for selective RAG analysis.

    Only indexes Division 8 specs and architectural drawings for faster,
    more relevant analysis. Falls back to full indexing if split documents
    not found.
    """
    rag = Division8RAGLocal(project_folder, openai_api_key)
    results = rag.analyze_project_selective()
    rag.save_results(results)
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python3 division8_rag_local.py <project_folder>")
        sys.exit(1)

    project_folder = Path(sys.argv[1])
    if not project_folder.exists():
        print(f"Error: Folder not found: {project_folder}")
        sys.exit(1)

    print(f"Analyzing Division 8 scope (LOCAL embeddings): {project_folder.name}")
    print("="*60)

    results = analyze_project_local(project_folder)
    print("\nResults:")
    print(json.dumps(results, indent=2))
