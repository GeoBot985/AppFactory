import fitz  # PyMuPDF
import os
from .embedder import embed_text
from .db import insert_chunk

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

def ingest_pdf(path: str, conn) -> dict:
    filename = os.path.basename(path)
    text = extract_text_from_pdf(path)
    chunks = chunk_text(text)

    chunks_indexed = 0
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        embedding = embed_text(chunk)
        insert_chunk(conn, filename, i, chunk, embedding)
        chunks_indexed += 1

    return {
        "doc_id": filename,
        "chunks_indexed": chunks_indexed
    }
