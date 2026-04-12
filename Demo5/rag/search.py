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


def _tokenize(s: str | None) -> set[str]:
    if not s:
        return set()
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return set(s.split())


def _normalize_identifier(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def _detect_identifier_like_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"\b[A-Za-z0-9-]+\b", query or "")
    detected = []
    for term in raw_terms:
        normalized = _normalize_identifier(term)
        if len(normalized) < 4:
            continue
        if re.search(r"[a-zA-Z]", term) and re.search(r"\d", term):
            detected.append(term)
    return list(dict.fromkeys(detected))


def _extract_query_phrases(query: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', query or "")
    if quoted:
        return [phrase.strip() for phrase in quoted if phrase.strip()]

    query = (query or "").strip()
    if len(query.split()) >= 3:
        return [query]
    return []


def score_lexical(query: str, text: str | None, document_name: str | None = None) -> float:
    if not query:
        return 0.0

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    text_tokens = _tokenize(text)
    matches = query_tokens.intersection(text_tokens)
    score = len(matches) / len(query_tokens)

    if document_name:
        doc_tokens = _tokenize(document_name)
        doc_matches = query_tokens.intersection(doc_tokens)
        if doc_matches:
            score += 0.1 * (len(doc_matches) / len(query_tokens))

    return min(score, 1.0)


def _score_lexical_full_corpus(query: str, item: dict) -> tuple[float, list[str]]:
    text = item.get("text") or ""
    text_lower = text.lower()
    match_types: list[str] = []
    lexical_score = score_lexical(query, text, item.get("document_name"))

    identifier_like_terms = _detect_identifier_like_terms(query)
    normalized_text = _normalize_identifier(text)
    normalized_doc_name = _normalize_identifier(item.get("document_name") or "")

    for term in identifier_like_terms:
        pattern = rf"\b{re.escape(term.lower())}\b"
        if re.search(pattern, text_lower):
            lexical_score = max(lexical_score, 1.0)
            match_types.append("exact_token")
        elif _normalize_identifier(term) and _normalize_identifier(term) in normalized_text:
            lexical_score = max(lexical_score, 0.95)
            match_types.append("normalized_token")
        elif _normalize_identifier(term) and _normalize_identifier(term) in normalized_doc_name:
            lexical_score = max(lexical_score, 0.85)
            match_types.append("filename_match")

    for phrase in _extract_query_phrases(query):
        phrase_lower = phrase.lower()
        if phrase_lower in text_lower:
            lexical_score = max(lexical_score, 1.0)
            match_types.append("exact_phrase")

    return min(lexical_score, 1.0), list(dict.fromkeys(match_types))


def _strong_lexical_hit(match_types: list[str]) -> bool:
    strong = {"exact_token", "normalized_token", "exact_phrase"}
    return any(match_type in strong for match_type in match_types)


def _collect_lexical_candidates(all_items: list[dict], query: str) -> tuple[list[dict], dict]:
    exact_hits = 0
    normalized_hits = 0
    phrase_hits = 0
    forced_hits = []
    lexical_candidates = []

    for item in all_items:
        lexical_score, match_types = _score_lexical_full_corpus(query, item)
        if lexical_score <= 0:
            continue

        candidate = {
            "item": item,
            "lexical_score": lexical_score,
            "match_types": match_types,
            "forced_include": _strong_lexical_hit(match_types),
        }
        lexical_candidates.append(candidate)

        if "exact_token" in match_types:
            exact_hits += 1
        if "normalized_token" in match_types:
            normalized_hits += 1
        if "exact_phrase" in match_types:
            phrase_hits += 1
        if candidate["forced_include"]:
            forced_hits.append(candidate)

    lexical_candidates.sort(
        key=lambda candidate: (candidate["forced_include"], candidate["lexical_score"]),
        reverse=True,
    )

    metrics = {
        "identifier_like_terms": _detect_identifier_like_terms(query),
        "exact_lexical_hits": exact_hits,
        "normalized_lexical_hits": normalized_hits,
        "phrase_hits": phrase_hits,
        "forced_included_chunks": len(forced_hits),
    }
    return lexical_candidates, metrics


def _merge_candidates(lexical_candidates: list[dict], vector_candidates: list[dict], candidate_pool_size: int) -> list[dict]:
    merged = {}

    for candidate in lexical_candidates:
        if candidate["forced_include"]:
            item = candidate["item"]
            key = (item["document_id"], item["chunk_index"], item["text"])
            merged[key] = {
                "item": item,
                "lexical_score": candidate["lexical_score"],
                "vector_score": 0.0,
                "match_types": candidate["match_types"],
                "forced_include": True,
            }

    for candidate in vector_candidates[:candidate_pool_size]:
        item = candidate["item"]
        key = (item["document_id"], item["chunk_index"], item["text"])
        existing = merged.get(key)
        if existing:
            existing["vector_score"] = candidate["vector_score"]
        else:
            merged[key] = {
                "item": item,
                "lexical_score": 0.0,
                "vector_score": candidate["vector_score"],
                "match_types": [],
                "forced_include": False,
            }

    for candidate in lexical_candidates:
        item = candidate["item"]
        key = (item["document_id"], item["chunk_index"], item["text"])
        if key in merged:
            merged[key]["lexical_score"] = max(merged[key]["lexical_score"], candidate["lexical_score"])
            merged[key]["match_types"] = list(dict.fromkeys(merged[key]["match_types"] + candidate["match_types"]))
            continue
        if len(merged) >= candidate_pool_size + len([c for c in lexical_candidates if c["forced_include"]]):
            break
        merged[key] = {
            "item": item,
            "lexical_score": candidate["lexical_score"],
            "vector_score": 0.0,
            "match_types": candidate["match_types"],
            "forced_include": candidate["forced_include"],
        }

    return list(merged.values())


def search(conn, query: str, top_k=5, document_ids: list[str] | None = None,
           vector_weight=0.7, lexical_weight=0.3, candidate_pool_size=20, per_doc_cap=2):
    all_embeddings_with_meta = get_all_embeddings(conn, document_ids=document_ids)
    region_mode = _query_region_mode(query)

    eligible_items = []
    for item in all_embeddings_with_meta:
        if region_mode == "table_row_preferred" and item.get("region_type") in {"summary_block", "pivot_like"}:
            continue
        eligible_items.append(item)

    lexical_candidates, lexical_metrics = _collect_lexical_candidates(eligible_items, query)

    query_embedding = embed_text(query)
    vector_candidates = []
    for item in eligible_items:
        v_score = cosine_similarity(query_embedding, item["embedding"])
        vector_candidates.append({
            "item": item,
            "vector_score": float(v_score),
        })
    vector_candidates.sort(key=lambda candidate: candidate["vector_score"], reverse=True)

    merged_candidates = _merge_candidates(lexical_candidates, vector_candidates, candidate_pool_size)

    scored_results = []
    for candidate in merged_candidates:
        item = candidate["item"]
        v_score = candidate["vector_score"]
        l_score = max(candidate["lexical_score"], score_lexical(query, item.get("text"), item.get("document_name")))
        region_boost = 0.0
        if region_mode == "table_row_preferred":
            if item.get("region_type") == "table_row":
                region_boost = 0.15
            elif item.get("region_type") == "header":
                region_boost = -0.05
        elif region_mode == "summary_allowed" and item.get("region_type") in {"summary_block", "pivot_like"}:
            region_boost = 0.1

        lexical_priority_boost = 0.25 if candidate["forced_include"] else 0.0
        final_score = (vector_weight * v_score) + (lexical_weight * l_score) + region_boost + lexical_priority_boost

        scored_results.append({
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
            "lexical_priority_boost": lexical_priority_boost,
            "match_types": candidate["match_types"],
            "forced_include": candidate["forced_include"],
            "score": float(final_score),
        })

    scored_results.sort(
        key=lambda result: (result["forced_include"], result["lexical_score"], result["score"]),
        reverse=True,
    )

    final_top_k = []
    doc_counts = {}
    for result in scored_results:
        doc_id = result["document_id"]
        count = doc_counts.get(doc_id, 0)
        if count < per_doc_cap:
            final_top_k.append(result)
            doc_counts[doc_id] = count + 1
        if len(final_top_k) >= top_k:
            break

    return {
        "results": final_top_k,
        "metrics": {
            "eligible_docs": len(set(item["document_id"] for item in eligible_items)),
            "eligible_chunk_count": len(eligible_items),
            "candidate_count": len(all_embeddings_with_meta),
            "pool_size": min(candidate_pool_size, len(vector_candidates)),
            "region_mode": region_mode,
            "lexical_prepass_run": True,
            "identifier_like_terms": lexical_metrics["identifier_like_terms"],
            "exact_lexical_hits": lexical_metrics["exact_lexical_hits"],
            "normalized_lexical_hits": lexical_metrics["normalized_lexical_hits"],
            "phrase_hits": lexical_metrics["phrase_hits"],
            "forced_included_chunks": lexical_metrics["forced_included_chunks"],
            "vector_candidate_count": len(vector_candidates[:candidate_pool_size]),
            "merged_candidate_count": len(merged_candidates),
        }
    }
