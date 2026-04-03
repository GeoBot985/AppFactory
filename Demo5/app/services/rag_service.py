import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, list_documents, delete_document, clear_corpus, get_corpus_stats
from rag.search import search

DB_PATH = "rag_v2.db"

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
    if not os.path.exists(DB_PATH):
        result["error"] = "knowledge base empty / unavailable"
        return result

    try:
        # Search function uses DuckDB connection to query chunks
        conn = get_connection(DB_PATH)
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

def delete_document_service(document_id: str) -> dict:
    try:
        conn = get_connection(DB_PATH)
        success = delete_document(conn, document_id)
        return {"ok": True, "deleted": success}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass

def clear_corpus_service() -> dict:
    try:
        conn = get_connection(DB_PATH)
        clear_corpus(conn)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass

def get_corpus_stats_service() -> dict:
    if not os.path.exists(DB_PATH):
        return {
            "ok": True,
            "stats": {
                "total_documents": 0,
                "total_chunks": 0,
                "last_ingestion_at": None
            }
        }
    try:
        conn = get_connection(DB_PATH)
        stats = get_corpus_stats(conn)
        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass

def list_indexed_documents() -> dict:
    """
    Returns:
    {
        "ok": bool,
        "documents": list[dict],
        "error": str | None
    }
    """
    if not os.path.exists(DB_PATH):
        return {
            "ok": True,
            "documents": [],
            "error": None
        }

    try:
        conn = get_connection(DB_PATH)
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
