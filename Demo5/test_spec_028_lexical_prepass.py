import unittest
from unittest.mock import patch

from rag.search import search


class TestSpec028LexicalPrepass(unittest.TestCase):
    @patch("rag.search.embed_text", return_value=[0.0, 1.0])
    @patch("rag.search.get_all_embeddings")
    def test_exact_identifier_hit_survives_vector_gating(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "General governance guidance without target token.",
                "embedding": [1.0, 0.0],
                "chunk_index": 0,
                "region_type": "paragraph",
                "sheet_name": None,
                "row_index": None,
                "cell_range": None,
                "document_id": "doc1",
                "document_name": "cobit.pdf",
                "ingested_at": "2026-01-01",
            },
            {
                "text": "APO13 covers managed security and risk responsibilities.",
                "embedding": [0.0, 0.1],
                "chunk_index": 1,
                "region_type": "paragraph",
                "sheet_name": None,
                "row_index": None,
                "cell_range": None,
                "document_id": "doc1",
                "document_name": "cobit.pdf",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(object(), "APO13", top_k=5, candidate_pool_size=1)

        self.assertTrue(any(item["chunk_index"] == 1 for item in result["results"]))
        self.assertEqual(result["metrics"]["exact_lexical_hits"], 1)
        self.assertEqual(result["metrics"]["forced_included_chunks"], 1)
        self.assertEqual(result["metrics"]["identifier_like_terms"], ["APO13"])

    @patch("rag.search.embed_text", return_value=[0.0, 1.0])
    @patch("rag.search.get_all_embeddings")
    def test_exact_phrase_hit_is_force_included(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "This chunk talks about unrelated governance wording.",
                "embedding": [1.0, 0.0],
                "chunk_index": 0,
                "region_type": "paragraph",
                "sheet_name": None,
                "row_index": None,
                "cell_range": None,
                "document_id": "doc1",
                "document_name": "docx.docx",
                "ingested_at": "2026-01-01",
            },
            {
                "text": 'The phrase "Compliance by Design" appears in this paragraph.',
                "embedding": [0.0, 0.2],
                "chunk_index": 1,
                "region_type": "paragraph",
                "sheet_name": None,
                "row_index": None,
                "cell_range": None,
                "document_id": "doc1",
                "document_name": "docx.docx",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(object(), '"Compliance by Design"', top_k=5, candidate_pool_size=1)

        self.assertTrue(any(item["chunk_index"] == 1 for item in result["results"]))
        self.assertGreaterEqual(result["metrics"]["phrase_hits"], 1)

    @patch("rag.search.embed_text", return_value=[0.0, 1.0])
    @patch("rag.search.get_all_embeddings")
    def test_merged_candidates_are_deduplicated(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "APO13 appears here.",
                "embedding": [0.0, 0.1],
                "chunk_index": 5,
                "region_type": "paragraph",
                "sheet_name": None,
                "row_index": None,
                "cell_range": None,
                "document_id": "doc1",
                "document_name": "cobit.pdf",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(object(), "APO13", top_k=5, candidate_pool_size=5)

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["metrics"]["merged_candidate_count"], 1)
