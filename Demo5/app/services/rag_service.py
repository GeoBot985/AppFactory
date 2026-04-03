import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection
from rag.search import search

def get_rag_context(query: str, top_k: int = 3) -> dict:
    """
    Returns:
    {
        "enabled": bool,
        "query": str,
        "chunks": list[str],
        "error": str | None
    }
    """
    result = {
        "enabled": True,
        "query": query,
        "chunks": [],
        "error": None
    }

    # We assume db is in Demo5/rag.db when running from Demo5
    db_path = "rag.db"
    if not os.path.exists(db_path):
        result["error"] = "knowledge base empty / unavailable"
        return result

    try:
        # Search function uses DuckDB connection to query chunks
        conn = get_connection(db_path)
        chunks = search(conn, query, top_k=top_k)
        result["chunks"] = chunks
    except Exception as e:
        result["error"] = str(e)
    finally:
        try:
            conn.close()
        except:
            pass

    return result
