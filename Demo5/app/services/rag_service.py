import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import (
    get_connection, list_documents, delete_document, clear_corpus,
    get_corpus_stats, get_document_by_id, get_all_chunks_for_document,
    find_exact_chunk
)
from rag.search import search
from app.config import (
    DB_PATH, VECTOR_WEIGHT, LEXICAL_WEIGHT,
    CANDIDATE_POOL_SIZE, PER_DOC_CAP
)


def verify_retrieved_chunks(conn, chunks: list[dict]) -> tuple[list[dict], int]:
    verified_chunks = []
    discarded_count = 0

    for chunk in chunks:
        exact_match = find_exact_chunk(
            conn,
            chunk["document_id"],
            chunk["chunk_index"],
            chunk["text"],
        )
        if exact_match:
            verified_chunks.append(chunk)
        else:
            discarded_count += 1

    return verified_chunks, discarded_count

def get_rag_context(query: str, top_k: int = 3, document_ids: list[str] | None = None) -> dict:
    """
    Returns:
    {
        "enabled": bool,
        "query": str,
        "chunks": list[dict],
        "metrics": dict | None,
        "error": str | None
    }
    """
    result = {
        "enabled": True,
        "query": query,
        "chunks": [],
        "metrics": {
            "eligible_docs": 0,
            "candidate_count": 0,
            "pool_size": 0,
            "verification_attempts": 0,
            "verified_chunks": 0,
            "discarded_unverified_chunks": 0,
            "verification_status": "not_run",
        },
        "error": None
    }

    # Default to DB_PATH from config
    if not os.path.exists(DB_PATH):
        result["error"] = "knowledge base empty / unavailable"
        return result

    try:
        # Search function uses DuckDB connection to query chunks
        conn = get_connection(DB_PATH)

        candidate_pool_size = max(CANDIDATE_POOL_SIZE, top_k)
        max_attempts = 3
        total_discarded = 0

        for attempt in range(1, max_attempts + 1):
            search_data = search(
                conn,
                query,
                top_k=top_k * attempt * 2,
                document_ids=document_ids,
                vector_weight=VECTOR_WEIGHT,
                lexical_weight=LEXICAL_WEIGHT,
                candidate_pool_size=candidate_pool_size,
                per_doc_cap=max(PER_DOC_CAP, top_k * attempt),
            )

            raw_chunks = search_data.get("results", [])
            verified_chunks, discarded_count = verify_retrieved_chunks(conn, raw_chunks)
            total_discarded += discarded_count

            metrics = search_data.get("metrics") or {}
            result["metrics"] = {
                "eligible_docs": metrics.get("eligible_docs", 0),
                "candidate_count": metrics.get("candidate_count", 0),
                "pool_size": metrics.get("pool_size", 0),
                "verification_attempts": attempt,
                "verified_chunks": len(verified_chunks),
                "discarded_unverified_chunks": total_discarded,
                "verification_status": "passed" if verified_chunks else "empty",
            }

            result["chunks"] = verified_chunks[:top_k]

            if len(result["chunks"]) >= top_k:
                break

            candidate_count = metrics.get("candidate_count", 0)
            if candidate_count and candidate_pool_size >= candidate_count:
                break

            candidate_pool_size = max(candidate_pool_size * 2, top_k * (attempt + 1) * 2)

        if not result["chunks"] and total_discarded > 0:
            result["metrics"]["verification_status"] = "all_discarded"

    except Exception as e:
        result["error"] = str(e)
    finally:
        try:
            conn.close()
        except:
            pass

    return result

def get_full_document_content(document_id: str) -> dict:
    """
    Reconstructs the full document text from its chunks.
    Returns:
    {
        "document_id": str,
        "document_name": str,
        "full_text": str,
        "chunk_count": int,
        "error": str | None
    }
    """
    result = {
        "document_id": document_id,
        "document_name": None,
        "full_text": "",
        "chunk_count": 0,
        "error": None
    }

    if not os.path.exists(DB_PATH):
        result["error"] = "knowledge base empty / unavailable"
        return result

    conn = None
    try:
        conn = get_connection(DB_PATH)
        doc = get_document_by_id(conn, document_id)
        if not doc:
            result["error"] = f"Document with ID {document_id} not found."
            return result

        result["document_name"] = doc["document_name"]
        chunks = get_all_chunks_for_document(conn, document_id)
        result["chunk_count"] = len(chunks)

        # Concatenate in order (get_all_chunks_for_document returns sorted by chunk_index)
        text_parts = [c["text"] for c in chunks]
        result["full_text"] = "\n".join(text_parts)

    except Exception as e:
        result["error"] = str(e)
    finally:
        if conn:
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
