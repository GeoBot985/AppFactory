import numpy as np
from .db import get_all_embeddings
from .embedder import embed_text

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def search(conn, query: str, top_k=5, document_ids: list[str] | None = None):
    query_embedding = embed_text(query)
    all_embeddings_with_meta = get_all_embeddings(conn, document_ids=document_ids)

    scored_results = []
    for item in all_embeddings_with_meta:
        score = cosine_similarity(query_embedding, item["embedding"])

        result = {
            "document_id": item["document_id"],
            "document_name": item["document_name"],
            "ingested_at": item["ingested_at"],
            "chunk_index": item["chunk_index"],
            "text": item["text"],
            "score": float(score)
        }
        scored_results.append(result)

    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:top_k]
