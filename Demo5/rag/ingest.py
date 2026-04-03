import fitz  # PyMuPDF
import os
import hashlib
import uuid
from datetime import datetime
from .embedder import embed_text
from .db import insert_document, insert_chunk
from .ocr_service import is_scanned_pdf, extract_text_with_ocr
from .docx_extractor import extract_docx_text

def get_file_hash(path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with fitz.open(path) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text

def chunk_text(text: str, chunk_size=500, overlap=50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks

def ingest_document(path: str, conn, document_name: str | None = None) -> dict:
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

    if ext == ".pdf":
        file_type = "pdf"
        text = extract_text_from_pdf(path)
        if is_scanned_pdf(len(text or "")):
            print("No usable embedded text found → using OCR fallback")
            ocr_result = extract_text_with_ocr(path)
            if ocr_result["error"]:
                raise ValueError(ocr_result["error"])

            text = ocr_result["text"]
            ocr_used = True
            ocr_char_count = ocr_result["ocr_char_count"]
            ocr_page_count = ocr_result["ocr_page_count"]
            ingestion_method = "ocr"

        if not text or not text.strip():
            raise ValueError("No extractable text found in PDF.")

    elif ext == ".docx":
        file_type = "docx"
        text = extract_docx_text(path)
        if not text or not text.strip():
            raise ValueError("No extractable text was found in this DOCX file.")
    else:
        # This shouldn't be reached if caller validates
        raise ValueError(f"Unsupported file type: {ext}")

    text_chunks = chunk_text(text)

    # We need to compute chunks first to know the count
    processed_chunks = []
    for i, text_chunk in enumerate(text_chunks):
        if not text_chunk.strip():
            continue

        embedding = embed_text(text_chunk)
        chunk_id = str(uuid.uuid4())

        processed_chunks.append({
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "chunk_index": i,
            "text": text_chunk,
            "embedding": embedding
        })

    chunk_count = len(processed_chunks)
    if chunk_count == 0:
        raise ValueError(f"No non-empty chunks could be created from {file_type.upper()} text.")

    # Create document record
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
        "ocr_page_count": ocr_page_count
    }

    # Insert into DB
    insert_document(conn, doc_record)
    for chunk in processed_chunks:
        insert_chunk(conn, chunk)

    return doc_record

def ingest_pdf(path: str, conn, document_name: str | None = None) -> dict:
    # Maintain for backward compatibility if needed, but it's just a wrapper now
    return ingest_document(path, conn, document_name)
