import pytest
from app.services.prompt_builder import build_grounded_prompt

def test_build_grounded_prompt_empty_chunks():
    query = "What is the capital of France?"
    prompt = build_grounded_prompt(query, [])

    assert "QUESTION:\nWhat is the capital of France?" in prompt
    assert "Insufficient information" in prompt
    assert "You have no context provided." in prompt

def test_build_grounded_prompt_with_chunks():
    query = "What color is the sky?"
    chunks = [
        {
            "document_name": "facts.pdf",
            "chunk_index": 0,
            "text": "The sky is blue."
        },
        {
            "document_name": "facts2.pdf",
            "chunk_index": 5,
            "text": "Grass is green."
        }
    ]

    prompt = build_grounded_prompt(query, chunks)

    # Assert query presence
    assert "QUESTION:\nWhat color is the sky?" in prompt

    # Assert context blocks
    assert "[Doc: facts.pdf | Chunk 0]" in prompt
    assert "The sky is blue." in prompt
    assert "[Doc: facts2.pdf | Chunk 5]" in prompt
    assert "Grass is green." in prompt

    # Assert instructions
    assert "Only use the provided context to answer the question." in prompt
    assert "Answer directly and concisely. Start with 'Yes' or 'No', then give a brief explanation." in prompt
    assert "You may make reasonable, minimal logical connections" in prompt
    assert "Insufficient information" in prompt
    assert "Do not use any prior knowledge or external frameworks not explicitly present in the context." in prompt
    assert "Do not guess or fill in large gaps." in prompt
    assert "Cite your sources for every claim using the format [Doc: name | Chunk X]." in prompt
