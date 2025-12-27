"""
RAG Engine using ChromaDB and Ollama embeddinggemma
"""
import os
import hashlib
import subprocess
import tempfile
import base64
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

import chromadb
from chromadb.config import Settings
import requests
import pandas as pd
import pypdf

from .config import (
    OLLAMA_BASE_URL, EMBEDDING_MODEL, EMBEDDING_DIM,
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K_RESULTS, CHROMA_DIR,
    DOC_PATTERNS, EMBEDDING_PROVIDER, OPENROUTER_API_KEY,
    OPENROUTER_EMBED_MODEL, OPENROUTER_EMBED_URL, EMBED_BATCH_SIZE,
    MAX_PDF_SIZE_MB, MAX_PDF_PAGES, PDFTEXT_FALLBACK_MB,
    DRAWING_SKIP_MAX_DIM_PT, EMBED_TIMEOUT_SECONDS
)

# Max PDF size/page limits (configured in config.py)


@dataclass
class Document:
    """Represents a document chunk"""
    content: str
    metadata: Dict
    doc_id: str = ""

    def __post_init__(self):
        if not self.doc_id:
            self.doc_id = hashlib.md5(
                f"{self.metadata.get('source', '')}-{self.content[:100]}".encode()
            ).hexdigest()


@dataclass
class ProjectIndex:
    """Index for a single project"""
    project_name: str
    project_path: Path
    collection: Optional[chromadb.Collection] = None
    documents: List[Document] = field(default_factory=list)
    file_manifest: Dict[str, Dict] = field(default_factory=dict)


class OllamaEmbeddings:
    """Ollama embedding client"""

    def __init__(self, model: str = EMBEDDING_MODEL, base_url: str = OLLAMA_BASE_URL, log_callback=None):
        self.model = model
        self.base_url = base_url
        self._log_callback = log_callback
        self._ensure_model()
        self._warmup()  # Pre-load model into memory

    def _log(self, msg: str):
        """Log to both console and callback"""
        print(msg, flush=True)
        if self._log_callback:
            self._log_callback(msg)

    def _warmup(self):
        """Pre-load model into GPU/memory"""
        self._log(f"[EMBED] Warming up {self.model}...")
        try:
            # Single embedding call with long keep_alive to load model
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": "warmup",
                    "keep_alive": "60m"  # Keep loaded for 60 mins
                },
                timeout=60
            )
            if response.status_code == 200:
                self._log(f"[EMBED] Model loaded and ready!")
            else:
                self._log(f"[EMBED] Warning: warmup failed")
        except Exception as e:
            self._log(f"[EMBED] Warning: warmup error: {e}")

    def unload(self):
        """Unload model from memory when done"""
        self._log(f"[EMBED] Unloading {self.model}...")
        try:
            requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": "",
                    "keep_alive": "0"  # Unload immediately
                },
                timeout=10
            )
            self._log(f"[EMBED] Model unloaded")
        except:
            pass

    def _ensure_model(self):
        """Pull model if not available"""
        self._log(f"[EMBED] Checking model: {self.model}")
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            models = [m["name"] for m in response.json().get("models", [])]
            model_names = [m.split(":")[0] for m in models]  # Strip :latest

            if self.model in models or f"{self.model}:latest" in models or self.model in model_names:
                self._log(f"[EMBED] Model ready!")
            else:
                self._log(f"[EMBED] Pulling {self.model}...")
                requests.post(f"{self.base_url}/api/pull", json={"name": self.model})
                self._log(f"[EMBED] Model pulled!")
        except Exception as e:
            self._log(f"[EMBED] WARNING: {e}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts - keeps model loaded"""
        embeddings = []
        total = len(texts)
        report_interval = max(1, total // 10)  # Report every 10%

        for idx, text in enumerate(texts):
            try:
                response = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text,
                        "keep_alive": "10m"  # Keep model loaded for 10 mins
                    },
                    timeout=EMBED_TIMEOUT_SECONDS
                )
                if response.status_code == 200:
                    embeddings.append(response.json()["embedding"])
                else:
                    self._log(f"[EMBED] WARNING: Failed {idx+1}/{total} (HTTP {response.status_code})")
                    embeddings.append([0.0] * EMBEDDING_DIM)
            except Exception as e:
                self._log(f"[EMBED] WARNING: Error {idx+1}/{total}: {e}")
                embeddings.append([0.0] * EMBEDDING_DIM)

            # Progress report every 10% or every 25 chunks
            if (idx + 1) % report_interval == 0 or (idx + 1) % 25 == 0:
                pct = ((idx + 1) / total) * 100
                self._log(f"[EMBED] Chunk {idx+1}/{total} ({pct:.0f}%)")

        return embeddings

    def embed_single(self, text: str) -> List[float]:
        """Embed a single text"""
        return self.embed([text])[0]


class OpenRouterEmbeddings:
    """OpenRouter embedding client"""

    def __init__(self, model: str, api_key: str, base_url: str, log_callback=None, batch_size: int = 150):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self._log_callback = log_callback

    def _log(self, msg: str):
        print(msg, flush=True)
        if self._log_callback:
            self._log_callback(msg)

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        try:
            resp = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            self._log(f"[EMBED] OpenRouter error: {e}")
            return [[0.0] * EMBEDDING_DIM for _ in texts]

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts with batching"""
        results = []
        total = len(texts)
        num_batches = (total + self.batch_size - 1) // self.batch_size

        for batch_num, i in enumerate(range(0, total, self.batch_size), 1):
            batch = texts[i:i + self.batch_size]
            embeddings = self._embed_batch(batch)
            if len(embeddings) < len(batch):
                missing = len(batch) - len(embeddings)
                embeddings.extend([[0.0] * EMBEDDING_DIM for _ in range(missing)])
            results.extend(embeddings)

            # Progress logging
            done = min(i + self.batch_size, total)
            pct = (done / total) * 100
            self._log(f"[EMBED] Batch {batch_num}/{num_batches}: {done}/{total} ({pct:.0f}%)")

        return results

    def embed_single(self, text: str) -> List[float]:
        return self.embed([text])[0]


class DocumentProcessor:
    """Process various document types into chunks"""

    def __init__(self, log_callback=None):
        self._log_callback = log_callback

    def _log(self, msg: str):
        """Log to both console and callback"""
        print(msg, flush=True)
        if self._log_callback:
            self._log_callback(msg)

    def extract_pdf_text(self, pdf_path: Path) -> str:
        """Fast PDF text extraction using pypdf; fallback to pdftotext for large files"""
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        self._log(f"[PDF] {pdf_path.name} ({file_size_mb:.1f}MB)")

        # Force pdftotext (all pages) for very large files to avoid pypdf OOM/kills
        if PDFTEXT_FALLBACK_MB and file_size_mb > PDFTEXT_FALLBACK_MB:
            self._log(f"[PDF] Size>{PDFTEXT_FALLBACK_MB}MB -> pdftotext (all pages)")
            try:
                result = subprocess.run(
                    ["pdftotext", "-layout", str(pdf_path), "-"],
                    capture_output=True, text=True, timeout=180
                )
                text = result.stdout
                self._log(f"[PDF] Done (pdftotext): {len(text):,} chars")
                return text
            except Exception as e:
                self._log(f"[PDF] pdftotext error: {e}")
                # fall through to pypdf attempt

        # Fallback for very large files: use pdftotext
        if MAX_PDF_SIZE_MB and file_size_mb > MAX_PDF_SIZE_MB:
            max_pages = MAX_PDF_PAGES if MAX_PDF_PAGES > 0 else None
            page_args = ["-l", str(max_pages)] if max_pages else []
            self._log(f"[PDF] Large file fallback -> pdftotext ({'all pages' if not max_pages else 'first ' + str(max_pages)})")
            try:
                result = subprocess.run(
                    ["pdftotext", "-layout", *page_args, str(pdf_path), "-"],
                    capture_output=True, text=True, timeout=120
                )
                text = result.stdout
                self._log(f"[PDF] Done (pdftotext): {len(text):,} chars")
                return text
            except Exception as e:
                self._log(f"[PDF] pdftotext error: {e}")
                return ""

        try:
            reader = pypdf.PdfReader(pdf_path)
            total_pages = len(reader.pages)
            max_pages = total_pages
            if MAX_PDF_PAGES and MAX_PDF_PAGES > 0 and total_pages > MAX_PDF_PAGES:
                max_pages = MAX_PDF_PAGES
                self._log(f"[PDF] Limiting to first {max_pages}/{total_pages} pages")

            self._log(f"[PDF] Extracting {max_pages} pages...")

            all_text = []
            report_interval = max(1, max_pages // 10)
            for i in range(max_pages):
                page = reader.pages[i]
                text = page.extract_text()
                if text:
                    all_text.append(text)
                if (i + 1) % report_interval == 0 or (i + 1) % 25 == 0:
                    pct = ((i + 1) / max_pages) * 100
                    self._log(f"[PDF] Page {i+1}/{max_pages} ({pct:.0f}%)")

            result = "\n".join(all_text)
            self._log(f"[PDF] Done: {len(result):,} chars")
            return result

        except Exception as e:
            self._log(f"[PDF] Error: {e}")
            return ""

    @staticmethod
    def extract_pdf_images(pdf_path: Path, dpi: int = 150) -> List[Tuple[int, str]]:
        """Extract PDF pages as base64 images for vision processing"""
        images = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Convert PDF to images
                subprocess.run(
                    ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), f"{tmpdir}/page"],
                    capture_output=True, timeout=120
                )
                # Read and encode images
                for img_path in sorted(Path(tmpdir).glob("*.png")):
                    page_num = int(img_path.stem.split("-")[-1])
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                        images.append((page_num, b64))
        except Exception as e:
            print(f"Error extracting PDF images: {e}")
        return images

    @staticmethod
    def extract_spreadsheet(file_path: Path) -> str:
        """Extract text from Excel/CSV files"""
        try:
            if file_path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path, sheet_name=None)
                text_parts = []
                for sheet_name, sheet_df in df.items():
                    text_parts.append(f"\n=== Sheet: {sheet_name} ===\n")
                    text_parts.append(sheet_df.to_string())
                return "\n".join(text_parts)
            elif file_path.suffix.lower() == ".csv":
                df = pd.read_csv(file_path)
                return df.to_string()
        except Exception as e:
            print(f"Error extracting spreadsheet: {e}")
        return ""

    @staticmethod
    def chunk_text_iter(text: str, chunk_size: int = CHUNK_SIZE,
                        overlap: int = CHUNK_OVERLAP):
        """Yield overlapping chunks to avoid large in-memory lists"""
        if not text:
            return

        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]

            # Try to break at paragraph or sentence boundary
            if end < text_len:
                last_para = chunk.rfind("\n\n")
                last_sentence = chunk.rfind(". ")
                if last_para > chunk_size * 0.5:
                    chunk = chunk[:last_para]
                elif last_sentence > chunk_size * 0.5:
                    chunk = chunk[:last_sentence + 1]

            chunk = chunk.strip()
            if chunk:
                yield chunk

            start += max(1, len(chunk) - overlap)

    @staticmethod
    def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
                   overlap: int = CHUNK_OVERLAP) -> List[str]:
        """Split text into overlapping chunks (retained for compatibility)"""
        return list(DocumentProcessor.chunk_text_iter(text, chunk_size, overlap))

    @staticmethod
    def classify_document(filename: str) -> str:
        """Classify document type based on filename"""
        fname_lower = filename.lower()
        for doc_type, patterns in DOC_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in fname_lower:
                    return doc_type
        return "other"


class RAGEngine:
    """Main RAG engine for project document indexing and retrieval"""

    def __init__(self, persist_dir: Path = CHROMA_DIR, log_callback=None):
        self._log_callback = log_callback
        self._log(f"[RAG] Initializing...")

        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # One persistent client per project (separate SQLite stores avoids lock contention)
        self.client_cache: Dict[str, chromadb.PersistentClient] = {}
        self._log(f"[RAG] ChromaDB base ready at {self.persist_dir}")

        # Choose embedding backend
        if EMBEDDING_PROVIDER.lower() == "openrouter":
            self.embeddings = OpenRouterEmbeddings(
                model=OPENROUTER_EMBED_MODEL,
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_EMBED_URL,
                log_callback=log_callback,
                batch_size=EMBED_BATCH_SIZE
            )
            self._log(f"[RAG] Using OpenRouter embeddings: {OPENROUTER_EMBED_MODEL}")
        else:
            self.embeddings = OllamaEmbeddings(
                model=EMBEDDING_MODEL,
                base_url=OLLAMA_BASE_URL,
                log_callback=log_callback
            )
            self._log(f"[RAG] Using Ollama embeddings: {EMBEDDING_MODEL}")

        self.processor = DocumentProcessor(log_callback=log_callback)
        self.project_indices: Dict[str, ProjectIndex] = {}
        self._log(f"[RAG] Engine ready!")

    def set_log_callback(self, callback):
        """Set/update the log callback"""
        self._log_callback = callback
        self.embeddings._log_callback = callback
        self.processor._log_callback = callback

    def _log(self, msg: str):
        """Log to both console and callback"""
        print(msg, flush=True)
        if self._log_callback:
            self._log_callback(msg)

    def _get_collection_name(self, project_name: str) -> str:
        """Generate valid collection name from project name"""
        # ChromaDB collection names must be 3-63 chars, alphanumeric with underscores
        name = "".join(c if c.isalnum() else "_" for c in project_name)
        name = name[:60]  # Leave room for uniqueness
        if len(name) < 3:
            name = name + "_project"
        return name

    def is_project_indexed(self, project_name: str) -> bool:
        """Check if project is already indexed in ChromaDB on disk"""
        collection_name = self._get_collection_name(project_name)
        project_store = self.persist_dir / collection_name
        # Check if folder exists and has files (ChromaDB creates chroma.sqlite3)
        if project_store.exists() and any(project_store.iterdir()):
            return True
        return False

    def get_or_create_project_index(self, project_path: Path) -> ProjectIndex:
        """Get or create an index for a project"""
        project_name = project_path.name

        if project_name in self.project_indices:
            return self.project_indices[project_name]

        collection_name = self._get_collection_name(project_name)
        # Ensure per-project Chroma store (separate SQLite files = safe concurrent index/query)
        project_store = self.persist_dir / collection_name
        project_store.mkdir(parents=True, exist_ok=True)

        if project_name not in self.client_cache:
            self.client_cache[project_name] = chromadb.PersistentClient(
                path=str(project_store),
                settings=Settings(anonymized_telemetry=False)
            )

        collection = self.client_cache[project_name].get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        index = ProjectIndex(
            project_name=project_name,
            project_path=project_path,
            collection=collection
        )
        self.project_indices[project_name] = index
        return index

    def index_project(self, project_path: Path,
                      progress_callback=None) -> ProjectIndex:
        """Index all documents in a project folder (streaming, per-file)"""
        self._log(f"[RAG] Indexing: {project_path.name}")

        index = self.get_or_create_project_index(project_path)

        # Find all documents
        pdf_files = list(project_path.rglob("*.pdf"))
        xlsx_files = list(project_path.rglob("*.xlsx")) + list(project_path.rglob("*.xls"))
        csv_files = list(project_path.rglob("*.csv"))
        all_files = pdf_files + xlsx_files + csv_files

        self._log(f"[RAG] Found: {len(pdf_files)} PDFs, {len(xlsx_files)} Excel, {len(csv_files)} CSV")

        # Deduplicate by content hash
        seen_hashes = set()
        unique_files = []
        for f in all_files:
            try:
                file_hash = hashlib.md5(f.read_bytes()).hexdigest()
                if file_hash not in seen_hashes:
                    seen_hashes.add(file_hash)
                    unique_files.append(f)
            except Exception:
                continue

        total_files = len(unique_files)
        self._log(f"[RAG] {total_files} unique files")

        if progress_callback:
            progress_callback(f"Found {total_files} unique documents", 0, total_files)

        total_chunks_indexed = 0

        # Process each file (embed as we go to avoid holding everything in memory)
        for i, file_path in enumerate(unique_files):
            pct = ((i + 1) / total_files) * 100
            self._log(f"[RAG] [{pct:5.1f}%] {i+1}/{total_files}: {file_path.name[:40]}")

            # Skip if already indexed in manifest with chunks
            manifest_key = str(file_path.relative_to(project_path))
            if manifest_key in index.file_manifest and index.file_manifest[manifest_key].get("chunks", 0) > 0:
                self._log(f"[RAG] Skipping already indexed file: {file_path.name}")
                if progress_callback:
                    progress_callback(
                        f"Skipped (already indexed) {file_path.name}",
                        i + 1,
                        total_files
                    )
                continue

            try:
                # Skip large-format drawing sheets based on first-page dimensions
                if file_path.suffix.lower() == ".pdf" and DRAWING_SKIP_MAX_DIM_PT and DRAWING_SKIP_MAX_DIM_PT > 0:
                    try:
                        reader_meta = pypdf.PdfReader(file_path, strict=False)
                        first_page = reader_meta.pages[0]
                        width = float(first_page.mediabox.width)
                        height = float(first_page.mediabox.height)
                        if max(width, height) >= DRAWING_SKIP_MAX_DIM_PT:
                            reason = f"page size {width:.0f}x{height:.0f} > {DRAWING_SKIP_MAX_DIM_PT}"
                            self._log(f"[RAG] Skipping drawing-size PDF: {file_path.name} ({reason})")
                            index.file_manifest[str(file_path.relative_to(project_path))] = {
                                "type": "drawing_skipped",
                                "chunks": 0,
                                "size": file_path.stat().st_size,
                                "reason": reason,
                            }
                            if progress_callback:
                                progress_callback(
                                    f"Skipped drawing PDF {file_path.name}",
                                    i + 1,
                                    total_files
                                )
                            continue
                    except Exception as e_meta:
                        self._log(f"[RAG] Warning: could not inspect page size {file_path.name}: {e_meta}")

                doc_type = self.processor.classify_document(file_path.name)

                # Extract text based on file type
                if file_path.suffix.lower() == ".pdf":
                    text = self.processor.extract_pdf_text(file_path)
                else:
                    text = self.processor.extract_spreadsheet(file_path)

                # Stream chunking to avoid large in-memory lists
                batch_size = EMBED_BATCH_SIZE
                batch_chunks = []
                total_file_chunks = 0

                for chunk in self.processor.chunk_text_iter(text):
                    total_file_chunks += 1
                    batch_chunks.append((total_file_chunks - 1, chunk))

                    if len(batch_chunks) >= batch_size:
                        batch_num = (total_file_chunks - 1) // batch_size
                        self._log(f"[EMBED] {file_path.name}: batch {batch_num+1} (stream, chunk {total_file_chunks})")

                        documents = []
                        metadatas = []
                        ids = []
                        seen_ids = set()
                        for chunk_index, chunk_text in batch_chunks:
                            doc = Document(
                                content=chunk_text,
                                metadata={
                                    "source": str(file_path.relative_to(project_path)),
                                    "filename": file_path.name,
                                    "doc_type": doc_type,
                                    "chunk_index": chunk_index,
                                    "total_chunks": 0,  # fill later
                                    "project": index.project_name
                                }
                            )
                            documents.append(doc.content)
                            metadatas.append(doc.metadata)
                            new_id = doc.doc_id
                            suffix = 1
                            while new_id in seen_ids:
                                new_id = f"{doc.doc_id}_{suffix}"
                                suffix += 1
                            seen_ids.add(new_id)
                            ids.append(new_id)

                        import time
                        t0 = time.time()
                        embeddings = self.embeddings.embed(documents)
                        t1 = time.time()
                        self._log(f"[EMBED] {file_path.name}: batch {batch_num+1} took {t1 - t0:.1f}s")

                        index.collection.add(
                            ids=ids,
                            embeddings=embeddings,
                            documents=documents,
                            metadatas=metadatas
                        )

                        total_chunks_indexed += len(documents)
                        batch_chunks = []

                        if progress_callback:
                            progress_callback(
                                f"[EMBED] {file_path.name} indexed {total_file_chunks} chunks",
                                i + 1,
                                total_files
                            )

                # Final partial batch
                if batch_chunks:
                    batch_num = total_file_chunks // batch_size
                    self._log(f"[EMBED] {file_path.name}: batch {batch_num+1} (final, chunk {total_file_chunks})")

                    documents = []
                    metadatas = []
                    ids = []
                    seen_ids = set()
                    for chunk_index, chunk_text in batch_chunks:
                        doc = Document(
                            content=chunk_text,
                            metadata={
                                "source": str(file_path.relative_to(project_path)),
                                "filename": file_path.name,
                                "doc_type": doc_type,
                                "chunk_index": chunk_index,
                                "total_chunks": 0,
                                "project": index.project_name
                            }
                        )
                        documents.append(doc.content)
                        metadatas.append(doc.metadata)
                        new_id = doc.doc_id
                        suffix = 1
                        while new_id in seen_ids:
                            new_id = f"{doc.doc_id}_{suffix}"
                            suffix += 1
                        seen_ids.add(new_id)
                        ids.append(new_id)

                    import time
                    t0 = time.time()
                    embeddings = self.embeddings.embed(documents)
                    t1 = time.time()
                    self._log(f"[EMBED] {file_path.name}: batch {batch_num+1} took {t1 - t0:.1f}s (final)")

                    index.collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas
                    )

                    total_chunks_indexed += len(documents)

                    if progress_callback:
                        progress_callback(
                            f"[EMBED] {file_path.name} indexed {total_file_chunks} chunks",
                            i + 1,
                            total_files
                        )

                # Update manifest with total chunks for this file
                index.file_manifest[str(file_path.relative_to(project_path))] = {
                    "type": doc_type,
                    "chunks": total_file_chunks,
                    "size": file_path.stat().st_size
                }

                if progress_callback:
                    progress_callback(
                        f"Processed {file_path.name}",
                        i + 1,
                        total_files
                    )

            except Exception as e:
                self._log(f"[RAG] ERROR: {file_path.name}: {e}")
                if progress_callback:
                    progress_callback(f"Error processing {file_path.name}: {e}", i + 1, total_files)

        self._log(f"[RAG] DONE: {project_path.name} - {total_chunks_indexed} chunks indexed")

        # We avoid storing all Document objects in memory
        index.documents = []
        return index

    def query(self, project_name: str, query: str,
              n_results: int = TOP_K_RESULTS,
              doc_types: Optional[List[str]] = None) -> List[Dict]:
        """Query the index for relevant documents"""
        if project_name not in self.project_indices:
            return []

        index = self.project_indices[project_name]

        # Embed query
        query_embedding = self.embeddings.embed_single(query)

        # Build where clause for filtering
        where = None
        if doc_types:
            where = {"doc_type": {"$in": doc_types}}

        # Query collection
        results = index.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        formatted = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                formatted.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "relevance": 1 - results["distances"][0][i]  # Cosine similarity
                })

        return formatted

    def query_by_section(self, project_name: str, section: str,
                         n_results: int = TOP_K_RESULTS) -> List[Dict]:
        """Query for specific Division 8 section content"""
        # Normalize section format
        section_clean = section.replace(" ", "").replace("-", "")
        queries = [
            f"Section {section}",
            f"SECTION {section}",
            section,
            section_clean
        ]

        all_results = []
        for q in queries:
            results = self.query(project_name, q, n_results=n_results // 2)
            all_results.extend(results)

        # Deduplicate and sort by relevance
        seen = set()
        unique_results = []
        for r in all_results:
            key = r["metadata"].get("source", "") + str(r["metadata"].get("chunk_index", 0))
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        return sorted(unique_results, key=lambda x: x["relevance"], reverse=True)[:n_results]

    def get_project_summary(self, project_name: str) -> Dict:
        """Get summary of indexed project"""
        if project_name not in self.project_indices:
            return {}

        index = self.project_indices[project_name]

        # Count documents by type using manifest (we don't keep all chunks in memory)
        type_counts = {}
        for _, info in index.file_manifest.items():
            doc_type = info.get("type", "other")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        total_chunks = sum(info.get("chunks", 0) for info in index.file_manifest.values())

        return {
            "project_name": project_name,
            "total_documents": total_chunks,
            "total_files": len(index.file_manifest),
            "document_types": type_counts,
            "file_manifest": index.file_manifest
        }

    def delete_project_index(self, project_name: str):
        """Delete a project's index"""
        if project_name in self.project_indices:
            collection_name = self._get_collection_name(project_name)
            try:
                client = self.client_cache.get(project_name)
                if client:
                    client.delete_collection(collection_name)
                # Optionally leave on-disk store; could be cleaned by caller if desired
            except Exception:
                pass
            self.project_indices.pop(project_name, None)
            self.client_cache.pop(project_name, None)


# Async wrapper for use in GUI
class AsyncRAGEngine:
    """Async wrapper for RAG engine operations"""

    def __init__(self, engine: RAGEngine):
        self.engine = engine
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def index_project(self, project_path: Path, progress_callback=None):
        """Async project indexing"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.engine.index_project(project_path, progress_callback)
        )

    async def query(self, project_name: str, query: str, **kwargs):
        """Async query"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.engine.query(project_name, query, **kwargs)
        )
