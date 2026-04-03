import unittest
from unittest.mock import patch, MagicMock
import requests
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from llm.ollama_adapter import OllamaAdapter, MoveParseError

class TestOllamaAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = OllamaAdapter(model_name="test_model", base_url="http://localhost:11434")

    @patch('requests.post')
    def test_valid_plain_uci(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "e2e4"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        move = self.adapter.get_move("prompt")
        self.assertEqual(move['parsed'], "e2e4")

    @patch('requests.post')
    def test_noisy_sentence_containing_uci(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "I choose g1f3 because it develops a knight."}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        move = self.adapter.get_move("prompt")
        self.assertEqual(move['parsed'], "g1f3")

    @patch('requests.post')
    def test_json_ish_junk_containing_move(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": '{"move":"d2d4"}'}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        move = self.adapter.get_move("prompt")
        self.assertEqual(move['parsed'], "d2d4")

    @patch('requests.post')
    def test_invalid_natural_language(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Move the king pawn two spaces"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        with self.assertRaises(MoveParseError) as ctx:
            self.adapter.get_move("prompt")
        self.assertEqual(ctx.exception.raw_response, "Move the king pawn two spaces")

    @patch('requests.post', side_effect=requests.exceptions.Timeout)
    def test_adapter_handles_timeout_cleanly(self, mock_post):
        with self.assertRaises(TimeoutError):
            self.adapter.get_move("prompt")

    @patch('requests.post', side_effect=requests.exceptions.ConnectionError)
    def test_adapter_handles_ollama_unavailable(self, mock_post):
        with self.assertRaises(ConnectionError):
            self.adapter.get_move("prompt")
    
    @patch('requests.post')
    def test_malformed_json_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        with self.assertRaises(RuntimeError):
            self.adapter.get_move("prompt")

    @patch('requests.get')
    def test_list_models_returns_installed_names(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5:3b"},
                {"name": "llama3.2:3b"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        models = OllamaAdapter.list_models("http://localhost:11434")
        self.assertEqual(models, ["qwen2.5:3b", "llama3.2:3b"])

if __name__ == '__main__':
    unittest.main()
