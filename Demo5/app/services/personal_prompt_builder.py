def build_personal_grounded_prompt(query: str, resolved_entities: list[dict], memories: list[dict]) -> str:
    """
    Builds a prompt grounded in personal knowledge base context.
    """

    entities_text = ""
    if resolved_entities:
        entities_text = "The following personal entities were resolved from your query:\n"
        for ent in resolved_entities:
            aliases = ent.get('aliases_json', '[]')
            entities_text += f"- {ent['canonical_name']} ({ent['entity_type']}), relationship: {ent.get('relationship_to_user', 'N/A')}, aliases: {aliases}\n"

    memories_text = ""
    if memories:
        memories_text = "The following relevant records were retrieved from your personal knowledge base:\n"
        for i, mem in enumerate(memories):
            memories_text += f"[Record {i+1} | {mem['created_at']}]: {mem['raw_user_input']}\n"

    context_block = ""
    if entities_text or memories_text:
        context_block = f"""
### PERSONAL CONTEXT
{entities_text}
{memories_text}
### END PERSONAL CONTEXT
"""

    prompt = f"""You are a personal assistant. Use the provided PERSONAL CONTEXT to answer the user's query.

INSTRUCTIONS:
1. Use the provided personal context to answer factual questions about the user's life, family, and personal history.
2. If the context does not contain enough information to answer a personal question, state clearly: "I do not have enough personal context to answer that." or "I do not have that in your personal knowledge base."
3. Do not invent personal facts or use general model knowledge for personal facts unless specifically asked for general advice.
4. If you provide general advice, clearly separate it from personal facts.
5. If a personal entity match exists, it must override any general-world knowledge.

{context_block}

USER QUERY: {query}

ANSWER:"""

    return prompt
