import os
import shutil
import sys
import uuid

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, init_db, list_documents, get_document_by_hash
from rag.ingest import ingest_pdf, get_file_hash


PERSISTENT_UPLOAD_DIR = os.path.abspath(
    os.path.join(demo5_root, "rag_uploads")
)


def _build_persistent_copy_path(source_path: str) -> str:
    os.makedirs(PERSISTENT_UPLOAD_DIR, exist_ok=True)
    filename = os.path.basename(source_path)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    return os.path.join(PERSISTENT_UPLOAD_DIR, unique_name)

def ingest_pdf_file(path: str, document_name: str | None = None) -> dict:
    """
    Returns:
    {
        "ok": bool,
        "path": str,
        "document_name": str,
        "status": "success" | "failed" | "skipped",
        "document_id": str | None,
        "chunks_indexed": int,
        "error": str | None,
        "reason": str | None
    }
    """
    display_name = document_name or os.path.basename(path)
    result = {
        "ok": False,
        "path": path,
        "document_name": display_name,
        "status": "failed",
        "document_id": None,
        "chunks_indexed": 0,
        "error": None,
        "reason": None
    }

    if not os.path.exists(path):
        result["error"] = "Selected file does not exist."
        return result

    db_path = "rag_v2.db"

    try:
        conn = get_connection(db_path)
        init_db(conn)

        # Optional Duplicate Detection
        file_hash = get_file_hash(path)
        existing_doc = get_document_by_hash(conn, file_hash)
        if existing_doc:
            result["ok"] = True
            result["status"] = "skipped"
            result["reason"] = "duplicate"
            result["document_id"] = existing_doc["document_id"]
            result["chunks_indexed"] = existing_doc["chunk_count"]
            return result

        persistent_path = _build_persistent_copy_path(path)
        shutil.copy2(path, persistent_path)

        try:
            ingest_result = ingest_pdf(
                persistent_path,
                conn,
                document_name=display_name,
            )
        except Exception:
            if os.path.exists(persistent_path):
                os.remove(persistent_path)
            raise

        result["ok"] = True
        result["status"] = "success"
        result["document_name"] = ingest_result.get("document_name", display_name)
        result["document_id"] = ingest_result.get("document_id")
        result["chunks_indexed"] = ingest_result.get("chunk_count", 0)
        result["path"] = ingest_result.get("source_path", persistent_path)

    except Exception as e:
        error_str = str(e)
        if "no extractable text" in error_str.lower() or "no non-empty chunks" in error_str.lower():
            result["error"] = "No extractable text was found in this PDF."
        elif "fitz" in error_str.lower() or "pdf" in error_str.lower() or "read" in error_str.lower() and "file" in error_str.lower():
            result["error"] = "Failed to read PDF."
        elif "embed" in error_str.lower() or "ollama" in error_str.lower():
            result["error"] = "Failed to generate embeddings."
        elif "sql" in error_str.lower() or "database" in error_str.lower() or "duckdb" in error_str.lower():
            result["error"] = "Failed to store document in knowledge base."
        else:
            result["error"] = f"Ingestion failed: {error_str}"
    finally:
        try:
            conn.close()
        except:
            pass

    return result

def get_indexed_docs() -> list[str]:
    """Returns a list of unique document IDs currently in the database."""
    db_path = "rag_v2.db"
    if not os.path.exists(db_path):
        return []

    docs = []
    try:
        conn = get_connection(db_path)
        # Check if table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        if any(t[0] == 'documents' for t in tables):
            doc_records = list_documents(conn)
            docs = [d["document_id"] for d in doc_records]
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except:
            pass

    return docs
