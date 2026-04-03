from typing import List, Dict

def build_grounded_prompt(query: str, retrieved_chunks: List[Dict]) -> str:
    """
    Constructs a strict grounding prompt.
    If there are no chunks, fallback behavior is handled prior to calling this or by returning a no-context prompt.
    """
    if not retrieved_chunks:
        return (
            f"QUESTION:\n{query}\n\n"
            f"INSTRUCTIONS:\n"
            f"- You have no context provided.\n"
            f"- Say exactly: 'Insufficient information' and nothing else.\n"
        )

    context_blocks = []
    for chunk in retrieved_chunks:
        doc_name = chunk.get("document_name", "Unknown")
        chunk_idx = chunk.get("chunk_index", "Unknown")
        text = chunk.get("text", "")
        block = f"[Doc: {doc_name} | Chunk {chunk_idx}]\n{text}"
        context_blocks.append(block)

    context_str = "\n\n".join(context_blocks)

    return (
        f"CONTEXT:\n\n{context_str}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Only use the provided context to answer the question.\n"
        f"- If the answer is not contained in the context, say exactly: 'Insufficient information'.\n"
        f"- Do not use prior knowledge.\n"
        f"- Do not guess or fill in gaps.\n"
        f"- Cite your sources for every claim using the format [Doc: name | Chunk X].\n"
    )
