import numpy as np
import re
from .db import get_all_embeddings
from .embedder import embed_text


def _query_region_mode(query: str) -> str:
    q = (query or "").lower()
    if any(term in q for term in ("top", "highest", "largest", "transactions", "expenses")):
        return "table_row_preferred"
    if any(term in q for term in ("total", "sum", "percentage")):
        return "summary_allowed"
    return "neutral"

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def score_lexical(query: str, text: str | None, document_name: str | None = None) -> float:
    """
    Simple lexical scoring based on term overlap.
    Case-insensitive, whitespace tokenization, punctuation stripping.
    """
    if not query:
        return 0.0

    # Clean and tokenize
    def tokenize(s):
        if not s:
            return set()
        s = str(s).lower()
        # Replace non-alphanumeric with spaces to properly separate tokens
        s = re.sub(r'[^a-z0-9\s]', ' ', s)
        return set(s.split())

    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    text_tokens = tokenize(text)

    # Term overlap in chunk text
    matches = query_tokens.intersection(text_tokens)
    score = len(matches) / len(query_tokens)

    # Optional small boost for filename matches
    if document_name:
        doc_tokens = tokenize(document_name)
        doc_matches = query_tokens.intersection(doc_tokens)
        if doc_matches:
            # Even if text has no matches, doc name might
            score += 0.1 * (len(doc_matches) / len(query_tokens))

    return min(score, 1.0)

def search(conn, query: str, top_k=5, document_ids: list[str] | None = None,
           vector_weight=0.7, lexical_weight=0.3, candidate_pool_size=20, per_doc_cap=2):

    query_embedding = embed_text(query)
    all_embeddings_with_meta = get_all_embeddings(conn, document_ids=document_ids)
    region_mode = _query_region_mode(query)

    # 1. Initial vector similarity search
    candidates = []
    for item in all_embeddings_with_meta:
        if region_mode == "table_row_preferred" and item.get("region_type") in {"summary_block", "pivot_like"}:
            continue
        v_score = cosine_similarity(query_embedding, item["embedding"])
        candidates.append({
            "item": item,
            "vector_score": float(v_score)
        })

    # Sort by vector score and take the pool
    candidates.sort(key=lambda x: x["vector_score"], reverse=True)
    pool = candidates[:candidate_pool_size]

    # 2. Hybrid ranking on the pool
    scored_results = []
    for entry in pool:
        item = entry["item"]
        v_score = entry["vector_score"]
        l_score = score_lexical(query, item.get("text"), item.get("document_name"))
        region_boost = 0.0
        if region_mode == "table_row_preferred":
            if item.get("region_type") == "table_row":
                region_boost = 0.15
            elif item.get("region_type") == "header":
                region_boost = -0.05
        elif region_mode == "summary_allowed" and item.get("region_type") in {"summary_block", "pivot_like"}:
            region_boost = 0.1

        # Normalize scores (vector is already ~0-1, lexical is 0-1)
        final_score = (vector_weight * v_score) + (lexical_weight * l_score) + region_boost

        result = {
            "document_id": item["document_id"],
            "document_name": item["document_name"],
            "ingested_at": item["ingested_at"],
            "chunk_index": item["chunk_index"],
            "text": item["text"],
            "region_type": item.get("region_type"),
            "sheet_name": item.get("sheet_name"),
            "row_index": item.get("row_index"),
            "cell_range": item.get("cell_range"),
            "vector_score": v_score,
            "lexical_score": l_score,
            "region_boost": region_boost,
            "score": float(final_score)
        }
        scored_results.append(result)

    scored_results.sort(key=lambda x: x["score"], reverse=True)

    # 3. Apply diversity rules (per_doc_cap)
    final_top_k = []
    doc_counts = {}
    for res in scored_results:
        doc_id = res["document_id"]
        count = doc_counts.get(doc_id, 0)
        if count < per_doc_cap:
            final_top_k.append(res)
            doc_counts[doc_id] = count + 1

        if len(final_top_k) >= top_k:
            break

    # Return structured metadata for debug too
    return {
        "results": final_top_k,
        "metrics": {
            "eligible_docs": len(set(item["document_id"] for item in all_embeddings_with_meta)),
            "candidate_count": len(all_embeddings_with_meta),
            "pool_size": len(pool),
            "region_mode": region_mode,
        }
    }
