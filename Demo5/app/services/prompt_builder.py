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
        f"- Do not claim that the document does not mention something unless the retrieved context explicitly supports that negative conclusion.\n"
        f"- If the question asks for an exact term or reference and the retrieved context does not show it directly, say exactly: 'Insufficient information'.\n"
        f"- Do not use any prior knowledge or external frameworks not explicitly present in the context.\n"
        f"- Do not guess or fill in large gaps.\n"
        f"- Cite your sources for every claim using the format [Doc: name | Chunk X].\n"
    )

def build_chat_with_document_prompt(query: str, document_name: str, full_text: str) -> str:
    """
    Constructs a prompt for Chat mode when a full document is provided as context.
    Allows for summarization, explanation, interpretation and Q&A over the whole document.
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

    return (
        f"{grounding_str}"
        f"DOCUMENT CONTEXT (Name: {document_name}):\n\n{full_text}\n\n"
        f"USER QUESTION:\n{query}\n\n"
        f"INSTRUCTIONS:\n"
        f"- You are in Chat mode with a full document as context.\n"
        f"- Use the provided document as your primary source of information.\n"
        f"- You may summarize, explain, interpret, and answer questions about the document as a whole.\n"
        f"- Your answers should be natural and conversational.\n"
        f"- If the answer is not supported by the document at all, say exactly: 'Insufficient information'.\n"
        f"- Do not use prior knowledge that contradicts or is not supported by the document for specific facts.\n"
    )
