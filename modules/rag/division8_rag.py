"""
Division 8 RAG System

Extracts Division 8 scope information from construction project documents
using RAG (Retrieval-Augmented Generation).

Architecture:
1. Chunk documents (PDFs + Word)
2. Embed chunks with OpenAI text-embedding-3-small
3. Store in ChromaDB (local)
4. Query with predefined Division 8 questions
5. Generate structured JSON output with GPT-4o-mini
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

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

# OpenAI for embeddings and generation
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
        "type": "",  # new construction, renovation, etc.
    },
    "windows": {
        "specified": True,
        "types": [],  # e.g., ["double hung", "awning", "fixed"]
        "manufacturers": [],
        "count_estimate": "",
        "performance_specs": {},  # U-factor, SHGC, etc.
        "notes": []
    },
    "doors": {
        "metal_doors": {
            "specified": True,
            "types": [],  # hollow metal, aluminum, stainless
            "count_estimate": "",
            "notes": []
        },
        "wood_doors_excluded": {
            "present_in_project": False,
            "note": ""  # "Wood doors by Division 6" etc.
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


# System prompt for Division 8 extraction
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


class Division8RAG:
    """
    RAG system for extracting Division 8 scope from project documents.
    """

    def __init__(
        self,
        project_folder: Path,
        openai_api_key: str = None,
        chroma_persist_dir: str = None
    ):
        """
        Initialize the RAG system.

        Args:
            project_folder: Path to project folder
            openai_api_key: OpenAI API key (or uses OPENAI_API_KEY env var)
            chroma_persist_dir: Directory to persist ChromaDB (default: project_folder/.chroma)
        """
        self.project_folder = Path(project_folder)
        self.project_id = self.project_folder.name

        # Set up OpenAI
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required")

        self.client = OpenAI(api_key=self.api_key)

        # Set up ChromaDB
        if chroma_persist_dir:
            self.chroma_dir = Path(chroma_persist_dir)
        else:
            self.chroma_dir = self.project_folder / ".chroma"

        self.chroma_dir.mkdir(exist_ok=True)

        # ChromaDB 0.6+ uses PersistentClient
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))

        # Collection name based on project
        self.collection_name = self._sanitize_collection_name(self.project_id)

        # Stats tracking
        self.stats = {
            'chunks_created': 0,
            'tokens_embedded': 0,
            'tokens_generated': 0,
            'api_calls': 0
        }

    def _sanitize_collection_name(self, name: str) -> str:
        """Sanitize project name for ChromaDB collection"""
        # ChromaDB collection names must be 3-63 chars, alphanumeric with underscores
        clean = ''.join(c if c.isalnum() else '_' for c in name.lower())
        clean = clean.strip('_')[:63]
        if len(clean) < 3:
            clean = clean + '_col'
        return clean

    def chunk_documents(self, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
        """
        Chunk all documents in the project folder.

        Args:
            chunk_size: Target size of each chunk in characters
            overlap: Overlap between chunks

        Returns:
            List of Chunk objects
        """
        chunks = []

        # Find all PDFs and Word docs
        pdf_files = list(self.project_folder.rglob("*.pdf"))
        docx_files = [f for f in self.project_folder.rglob("*.docx") if not f.name.startswith('~$')]

        logger.info(f"[RAG] Found {len(pdf_files)} PDFs and {len(docx_files)} Word docs")

        # Process PDFs
        for pdf_path in pdf_files:
            pdf_chunks = self._chunk_pdf(pdf_path, chunk_size, overlap)
            chunks.extend(pdf_chunks)

        # Process Word docs
        for docx_path in docx_files:
            docx_chunks = self._chunk_docx(docx_path, chunk_size, overlap)
            chunks.extend(docx_chunks)

        self.stats['chunks_created'] = len(chunks)
        logger.info(f"[RAG] Created {len(chunks)} chunks total")

        return chunks

    def _chunk_pdf(self, pdf_path: Path, chunk_size: int, overlap: int) -> List[Chunk]:
        """Extract and chunk text from a PDF"""
        chunks = []

        if not PDF_AVAILABLE:
            logger.warning("pdfplumber not available, skipping PDF")
            return chunks

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""

                    if not text.strip():
                        continue

                    # Classify chunk type based on content
                    chunk_type = self._classify_content(text, pdf_path.name)

                    # Create chunks from page text
                    page_chunks = self._split_text(
                        text,
                        chunk_size,
                        overlap,
                        source_file=pdf_path.name,
                        page_num=page_num,
                        chunk_type=chunk_type
                    )
                    chunks.extend(page_chunks)

        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}: {e}")

        return chunks

    def _chunk_docx(self, docx_path: Path, chunk_size: int, overlap: int) -> List[Chunk]:
        """Extract and chunk text from a Word document"""
        chunks = []

        if not DOCX_AVAILABLE:
            logger.warning("python-docx not available, skipping Word doc")
            return chunks

        try:
            doc = Document(str(docx_path))
            full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())

            chunk_type = self._classify_content(full_text, docx_path.name)

            chunks = self._split_text(
                full_text,
                chunk_size,
                overlap,
                source_file=docx_path.name,
                page_num=0,
                chunk_type=chunk_type
            )

        except Exception as e:
            logger.error(f"Error processing {docx_path.name}: {e}")

        return chunks

    def _classify_content(self, text: str, filename: str) -> str:
        """Classify content type based on text and filename"""
        text_lower = text.lower()
        name_lower = filename.lower()

        # Check for spec sections
        if any(x in text_lower for x in ['section 08', 'csi 08', '08 11 00', '08 14 00', '08 71 00']):
            return 'spec'

        # Check for schedules
        if any(x in text_lower for x in ['door schedule', 'window schedule', 'hardware schedule']):
            return 'schedule'

        # Check for bid invite
        if any(x in name_lower for x in ['invite', 'itb', 'rfp', 'bid']):
            return 'bid_invite'

        # Check for drawings
        if any(x in name_lower for x in ['drawing', 'plan', 'elevation', 'detail']):
            return 'drawing'

        return 'other'

    def _split_text(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
        source_file: str,
        page_num: int,
        chunk_type: str
    ) -> List[Chunk]:
        """Split text into overlapping chunks"""
        chunks = []

        if len(text) <= chunk_size:
            # Single chunk
            chunk_id = hashlib.md5(f"{source_file}:{page_num}:0".encode()).hexdigest()[:12]
            chunks.append(Chunk(
                text=text,
                source_file=source_file,
                page_num=page_num,
                chunk_id=chunk_id,
                chunk_type=chunk_type
            ))
        else:
            # Multiple chunks with overlap
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
        """
        Embed chunks and store in ChromaDB.

        Args:
            chunks: List of Chunk objects to embed
        """
        # Get or create collection
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"project_id": self.project_id}
            )
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            # Try with simpler settings
            self.chroma_client = chromadb.Client()
            collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name
            )

        # Embed in batches
        batch_size = 100
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

            # Get embeddings from OpenAI
            try:
                response = self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts
                )
                embeddings = [e.embedding for e in response.data]

                self.stats['api_calls'] += 1
                self.stats['tokens_embedded'] += response.usage.total_tokens

                # Add to collection
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas
                )

                logger.info(f"[RAG] Embedded batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")

            except Exception as e:
                logger.error(f"Error embedding batch: {e}")

        # PersistentClient auto-persists, no need to call persist()

    def retrieve(self, query: str, n_results: int = 20) -> List[Dict]:
        """
        Retrieve relevant chunks for a query.

        Args:
            query: Search query
            n_results: Number of results to return

        Returns:
            List of dicts with text and metadata
        """
        try:
            collection = self.chroma_client.get_collection(self.collection_name)
        except Exception as e:
            logger.error(f"Collection not found: {e}")
            return []

        # Embed query
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=[query]
        )
        query_embedding = response.data[0].embedding
        self.stats['api_calls'] += 1

        # Query collection
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        # Format results
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
        """
        Generate Division 8 scope summary from retrieved chunks.

        Args:
            retrieved_chunks: List of relevant chunk dicts

        Returns:
            Structured Division 8 scope dict
        """
        # Build context from chunks
        context_parts = []
        for chunk in retrieved_chunks:
            source = chunk['metadata'].get('source_file', 'unknown')
            page = chunk['metadata'].get('page_num', 0)
            chunk_type = chunk['metadata'].get('chunk_type', 'other')
            context_parts.append(f"[{chunk_type.upper()}] {source} (p.{page}):\n{chunk['text']}\n")

        context = "\n---\n".join(context_parts)

        # Build prompt
        system = SYSTEM_PROMPT.format(schema=json.dumps(DIVISION_8_SCHEMA, indent=2))

        user_prompt = f"""Analyze the following construction document excerpts and extract the Division 8 (Openings) scope information.

DOCUMENT EXCERPTS:
{context}

Based on these documents, provide a comprehensive Division 8 scope summary as JSON."""

        # Call GPT-4o-mini
        try:
            response = self.client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
                # Note: gpt-5-nano doesn't support temperature parameter
            )

            self.stats['api_calls'] += 1
            self.stats['tokens_generated'] += response.usage.total_tokens

            # Parse response
            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {"error": str(e)}

    def analyze_project(self) -> Dict:
        """
        Full RAG pipeline: chunk, embed, retrieve, generate.

        Returns:
            Division 8 scope summary dict
        """
        logger.info(f"[RAG] Starting analysis for: {self.project_id}")

        # Step 1: Chunk documents
        chunks = self.chunk_documents()

        if not chunks:
            return {"error": "No documents found to analyze"}

        # Step 2: Embed and store
        self.embed_and_store(chunks)

        # Step 3: Retrieve relevant chunks
        query = "Division 8 windows doors hardware specifications schedule openings glazing storefront entrance"
        retrieved = self.retrieve(query, n_results=30)

        logger.info(f"[RAG] Retrieved {len(retrieved)} relevant chunks")

        # Step 4: Generate summary
        summary = self.generate_scope_summary(retrieved)

        # Add metadata
        summary['_rag_metadata'] = {
            'project_id': self.project_id,
            'chunks_analyzed': len(chunks),
            'chunks_retrieved': len(retrieved),
            'stats': self.stats
        }

        return summary

    def save_results(self, results: Dict, output_path: Path = None) -> Path:
        """Save analysis results to JSON file"""
        if output_path is None:
            output_path = self.project_folder / "division8_scope.json"

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"[RAG] Saved results to {output_path}")
        return output_path


def analyze_project_division8(project_folder: Path, openai_api_key: str = None) -> Dict:
    """
    Convenience function to analyze a project's Division 8 scope.

    Args:
        project_folder: Path to project folder
        openai_api_key: Optional API key (uses env var if not provided)

    Returns:
        Division 8 scope summary dict
    """
    rag = Division8RAG(project_folder, openai_api_key)
    results = rag.analyze_project()
    rag.save_results(results)
    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) < 2:
        print("Usage: python3 division8_rag.py <project_folder>")
        sys.exit(1)

    project_folder = Path(sys.argv[1])

    if not project_folder.exists():
        print(f"Error: Folder not found: {project_folder}")
        sys.exit(1)

    print(f"Analyzing Division 8 scope for: {project_folder.name}")
    print("="*60)

    results = analyze_project_division8(project_folder)

    print("\nResults:")
    print(json.dumps(results, indent=2))
