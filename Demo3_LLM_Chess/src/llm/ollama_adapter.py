import requests
import re


class MoveParseError(ValueError):
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


class OllamaAdapter:
    def __init__(self, model_name: str, base_url: str, timeout: int = 30):
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout

    def get_response(self, prompt: str) -> str:
        api_url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post(api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Ollama server not reachable at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama model response exceeded {self.timeout} seconds")
        
        try:
            response_json = response.json()
        except requests.exceptions.JSONDecodeError:
            raise RuntimeError("Ollama returned malformed JSON payload")

        return response_json.get("response", "")

    def get_move(self, prompt: str) -> dict:
        raw_response = self.get_response(prompt)

        # \b[a-h][1-8][a-h][1-8][qrbn]?\b
        match = re.search(r"\b[a-h][1-8][a-h][1-8][qrbn]?\b", raw_response.lower())

        if match:
            parsed_move = match.group(0)
            return {"raw": raw_response, "parsed": parsed_move}
        else:
            raise MoveParseError("No valid UCI move found in model response", raw_response=raw_response)

    @classmethod
    def list_models(cls, base_url: str, timeout: int = 30) -> list[str]:
        api_url = f"{base_url}/api/tags"
        try:
            response = requests.get(api_url, timeout=timeout)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Ollama server not reachable at {base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama model listing exceeded {timeout} seconds")

        try:
            response_json = response.json()
        except requests.exceptions.JSONDecodeError:
            raise RuntimeError("Ollama returned malformed JSON payload")

        models = response_json.get("models", [])
        return [model["name"] for model in models if model.get("name")]
