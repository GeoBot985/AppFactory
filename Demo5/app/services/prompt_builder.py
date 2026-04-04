from typing import List, Dict, Optional
from app.services.session_grounding import get_session_grounding

def build_grounded_prompt(query: str, retrieved_chunks: List[Dict]) -> str:
    """
    Constructs a strict but slightly more reasonable grounding prompt.
    """
    grounding = get_session_grounding()
    grounding_str = ""
    if grounding:
        grounding_str = (
            f"AGENT CONTEXT:\n"
            f"- Current Datetime: {grounding.get('current_datetime')}\n"
            f"- Timezone: {grounding.get('timezone')}\n"
            f"- Location: {grounding.get('location')}\n"
            f"- Purpose: {grounding.get('agent_purpose')}\n\n"
        )

    if not retrieved_chunks:
        return (
            f"{grounding_str}"
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
        f"{grounding_str}"
        f"CONTEXT:\n\n{context_str}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Only use the provided context to answer the question.\n"
        f"- Answer directly and concisely. Start with 'Yes' or 'No', then give a brief explanation.\n"
        f"- You may make reasonable, minimal logical connections between closely related concepts present in the context "
        f"(for example, connecting 'least privilege' or access rights to the idea of using multiple accounts when the "
        f"relationship is directly implied by the text).\n"
        f"- If the answer is not supported by the context at all, say exactly: 'Insufficient information'.\n"
        f"- Do not use any prior knowledge or external frameworks not explicitly present in the context.\n"
        f"- Do not guess or fill in large gaps.\n"
        f"- Cite your sources for every claim using the format [Doc: name | Chunk X].\n"
    )
