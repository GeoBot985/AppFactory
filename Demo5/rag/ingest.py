import fitz  # PyMuPDF
import os
import hashlib
import uuid
from datetime import datetime
from .embedder import embed_text
from .db import insert_document, insert_chunk

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

def ingest_pdf(path: str, conn, document_name: str | None = None) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    doc_name = document_name or os.path.basename(path)
    file_hash = get_file_hash(path)
    file_size = os.path.getsize(path)
    ingested_at = datetime.utcnow().isoformat()
    doc_id = str(uuid.uuid4())

    text = extract_text_from_pdf(path)
    if not text or not text.strip():
        raise ValueError("No extractable text found in PDF.")

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
        raise ValueError("No non-empty chunks could be created from PDF text.")

    # Create document record
    doc_record = {
        "document_id": doc_id,
        "document_name": doc_name,
        "source_path": os.path.abspath(path),
        "file_hash": file_hash,
        "file_size_bytes": file_size,
        "ingested_at": ingested_at,
        "chunk_count": chunk_count
    }

    # Insert into DB
    insert_document(conn, doc_record)
    for chunk in processed_chunks:
        insert_chunk(conn, chunk)

    return doc_record
