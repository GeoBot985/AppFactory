import fitz
import hashlib
import os
import uuid
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .db import insert_chunk, insert_document
from .docx_extractor import extract_docx_text
from .embedder import embed_text
from .ocr_service import extract_text_with_ocr, is_scanned_pdf
from .timing import IngestionTimings, StageTimer
from app.config import INGESTION_MAX_WORKERS, INGESTION_EMBED_MAX_WORKERS


def get_file_hash(path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for byte_block in iter(lambda: file_handle.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


class ExtractionProgressTracker:
    def __init__(self, total_pages: int):
        self.total_pages = total_pages
        self.completed_pages = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            self.completed_pages += 1
            print(f"Ingestion Progress | mode: text | pages: {self.completed_pages}/{self.total_pages} complete")

def _extract_page_text(path: str, page_index: int, tracker: ExtractionProgressTracker | None = None) -> tuple[int, str]:
    with fitz.open(path) as doc:
        page = doc[page_index]
        text = page.get_text()
        if tracker:
            tracker.increment()
        return page_index, text


def extract_text_from_pdf_parallel(path: str, max_workers: int = INGESTION_MAX_WORKERS) -> str:
    with fitz.open(path) as doc:
        page_count = len(doc)

    tracker = ExtractionProgressTracker(page_count)
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_extract_page_text, path, i, tracker) for i in range(page_count)]
        for future in futures:
            results.append(future.result())

    # Sort by page index
    results.sort(key=lambda x: x[0])
    return "\n".join([r[1] for r in results])


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _embed_chunk(task: tuple[int, str, str]) -> dict | None:
    index, text_chunk, doc_id = task
    if not text_chunk.strip():
        return None

    embedding = embed_text(text_chunk)
    return {
        "chunk_id": str(uuid.uuid4()),
        "document_id": doc_id,
        "chunk_index": index,
        "text": text_chunk,
        "embedding": embedding,
    }


def ingest_document(path: str, conn, document_name: str | None = None) -> dict:
    timings = IngestionTimings()
    timings.start_total()

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    doc_name = document_name or os.path.basename(path)
    file_hash = get_file_hash(path)
    file_size = os.path.getsize(path)
    ingested_at = datetime.utcnow().isoformat()
    doc_id = str(uuid.uuid4())

    ext = os.path.splitext(path)[1].lower()
    text = ""
    ocr_used = False
    ocr_char_count = 0
    ocr_page_count = 0
    ingestion_method = "text"
    file_type = "unknown"
    failed_pages = []

    with StageTimer(timings, "open_pdf"):
        # Just to check if it's a valid PDF and get page count early if needed
        # but the actual opening happens inside extraction functions too.
        if ext == ".pdf":
            try:
                with fitz.open(path) as doc:
                    ocr_page_count = len(doc)
            except Exception as e:
                raise ValueError(f"Failed to open PDF: {e}")

    if ext == ".pdf":
        file_type = "pdf"

        with StageTimer(timings, "extract_text"):
            text = extract_text_from_pdf_parallel(path)

        if is_scanned_pdf(len(text or "")):
            print("No usable embedded text found; using OCR fallback")

            # Reset timings for OCR
            timings.record_stage("extract_text", 0.0)

            with StageTimer(timings, "ocr_full_process"):
                ocr_result = extract_text_with_ocr(path, max_workers=INGESTION_MAX_WORKERS)

            if ocr_result["error"]:
                raise ValueError(ocr_result["error"])

            text = ocr_result["text"]
            ocr_used = True
            ocr_char_count = ocr_result["ocr_char_count"]
            ocr_page_count = ocr_result["ocr_page_count"]
            failed_pages = ocr_result.get("failed_pages", [])
            ingestion_method = "ocr"

            # Merge granular OCR timings if present
            if "granular_timings" in ocr_result:
                for k, v in ocr_result["granular_timings"].items():
                    timings.record_stage(k, v)

        if not text or not text.strip():
            raise ValueError("No extractable text found in PDF.")

    elif ext == ".docx":
        file_type = "docx"
        with StageTimer(timings, "extract_text"):
            text = extract_docx_text(path)
        if not text or not text.strip():
            raise ValueError("No extractable text was found in this DOCX file.")

    else:
        raise ValueError(f"Unsupported file type: {ext}")

    with StageTimer(timings, "cleanup"):
        # Placeholder for cleanup if any specific is needed beyond stripping in OCR
        pass

    with StageTimer(timings, "chunking"):
        text_chunks = chunk_text(text)

    processed_chunks = []
    with StageTimer(timings, "embedding"):
        embed_tasks = [
            (index, text_chunk, doc_id)
            for index, text_chunk in enumerate(text_chunks)
            if text_chunk.strip()
        ]

        with ThreadPoolExecutor(max_workers=INGESTION_EMBED_MAX_WORKERS) as executor:
            for embedded_chunk in executor.map(_embed_chunk, embed_tasks):
                if embedded_chunk:
                    processed_chunks.append(embedded_chunk)

        processed_chunks.sort(key=lambda chunk: chunk["chunk_index"])

    chunk_count = len(processed_chunks)
    if chunk_count == 0:
        raise ValueError(f"No non-empty chunks could be created from {file_type.upper()} text.")

    doc_record = {
        "document_id": doc_id,
        "document_name": doc_name,
        "source_path": os.path.abspath(path),
        "file_hash": file_hash,
        "file_size_bytes": file_size,
        "ingested_at": ingested_at,
        "chunk_count": chunk_count,
        "ingestion_method": ingestion_method,
        "file_type": file_type,
        "ocr_used": ocr_used,
        "ocr_char_count": ocr_char_count,
        "ocr_page_count": ocr_page_count,
    }

    with StageTimer(timings, "db_write"):
        insert_document(conn, doc_record)
        for chunk in processed_chunks:
            insert_chunk(conn, chunk)

    doc_record["timings"] = timings.get_summary()
    doc_record["failed_pages"] = failed_pages
    doc_record["max_workers"] = INGESTION_MAX_WORKERS
    doc_record["embed_max_workers"] = INGESTION_EMBED_MAX_WORKERS

    return doc_record


def ingest_pdf(path: str, conn, document_name: str | None = None) -> dict:
    return ingest_document(path, conn, document_name)
