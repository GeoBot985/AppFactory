import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, init_db, list_documents
from rag.ingest import ingest_pdf

def ingest_pdf_file(path: str) -> dict:
    """
    Returns:
    {
        "ok": bool,
        "path": str,
        "doc_id": str | None,
        "chunks_indexed": int,
        "error": str | None
    }
    """
    result = {
        "ok": False,
        "path": path,
        "doc_id": None,
        "chunks_indexed": 0,
        "error": None
    }

    if not os.path.exists(path):
        result["error"] = "Selected file does not exist."
        return result

    db_path = "rag_v2.db"

    try:
        conn = get_connection(db_path)
        init_db(conn)

        # ingest_pdf now returns a full doc record
        ingest_result = ingest_pdf(path, conn)

        result["ok"] = True
        result["doc_id"] = ingest_result.get("document_id")
        result["chunks_indexed"] = ingest_result.get("chunk_count", 0)

    except Exception as e:
        error_str = str(e)
        if "fitz" in error_str.lower() or "pdf" in error_str.lower() or "read" in error_str.lower() and "file" in error_str.lower():
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
