import numpy as np
from .db import get_all_embeddings
from .embedder import embed_text

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def search(conn, query: str, top_k=5):
    query_embedding = embed_text(query)
    all_embeddings = get_all_embeddings(conn)

    scored_results = []
    for text, embedding in all_embeddings:
        score = cosine_similarity(query_embedding, embedding)
        scored_results.append((score, text))

    scored_results.sort(key=lambda x: x[0], reverse=True)

    top_results = []
    for score, text in scored_results[:top_k]:
        top_results.append(text)

    return top_results
