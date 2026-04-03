import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, list_documents
from rag.search import search

def get_rag_context(query: str, top_k: int = 3, document_ids: list[str] | None = None) -> dict:
    """
    Returns:
    {
        "enabled": bool,
        "query": str,
        "chunks": list[dict],
        "error": str | None
    }
    """
    result = {
        "enabled": True,
        "query": query,
        "chunks": [],
        "error": None
    }

    # Default to rag_v2.db
    db_path = "rag_v2.db"
    if not os.path.exists(db_path):
        result["error"] = "knowledge base empty / unavailable"
        return result

    try:
        # Search function uses DuckDB connection to query chunks
        conn = get_connection(db_path)
        # Modified to pass document_ids and return dicts
        search_results = search(conn, query, top_k=top_k, document_ids=document_ids)
        result["chunks"] = search_results
    except Exception as e:
        result["error"] = str(e)
    finally:
        try:
            conn.close()
        except:
            pass

    return result

def list_indexed_documents() -> dict:
    """
    Returns:
    {
        "ok": bool,
        "documents": list[dict],
        "error": str | None
    }
    """
    db_path = "rag_v2.db"
    if not os.path.exists(db_path):
        return {
            "ok": True,
            "documents": [],
            "error": None
        }

    try:
        conn = get_connection(db_path)
        docs = list_documents(conn)
        return {
            "ok": True,
            "documents": docs,
            "error": None
        }
    except Exception as e:
        return {
            "ok": False,
            "documents": [],
            "error": str(e)
        }
    finally:
        try:
            conn.close()
        except:
            pass
