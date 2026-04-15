from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request


@dataclass(frozen=True)
class OllamaRunSnapshot:
    model: str
    prompt: str


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def list_models(self) -> list[str]:
        endpoint = f"{self.base_url}/api/tags"
        try:
            with request.urlopen(endpoint, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except error.URLError as exc:
            raise ConnectionError(f"Ollama server not reachable at {self.base_url}") from exc
        except TimeoutError as exc:
            raise TimeoutError(f"Ollama model listing exceeded {self.timeout} seconds") from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned malformed JSON payload") from exc

        models = data.get("models")
        if not isinstance(models, list):
            raise RuntimeError("Ollama model list payload is malformed")

        return [item["name"] for item in models if isinstance(item, dict) and item.get("name")]

    def create_snapshot(self, model: str, prompt: str) -> OllamaRunSnapshot:
        return OllamaRunSnapshot(model=model, prompt=prompt)

    def run_prompt_stream(self, snapshot: OllamaRunSnapshot):
        endpoint = f"{self.base_url}/api/generate"
        payload = json.dumps(
            {
                "model": snapshot.model,
                "prompt": snapshot.prompt,
                "stream": True,
            }
        ).encode("utf-8")
        req = request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout * 20) as response:
                for raw_line in response:
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        yield {"type": "warning", "message": "Malformed streaming response chunk received."}
                        continue

                    if "error" in data and data["error"]:
                        raise RuntimeError(str(data["error"]))

                    chunk = data.get("response", "")
                    if chunk:
                        yield {"type": "chunk", "text": chunk}

                    if data.get("done"):
                        yield {
                            "type": "done",
                            "done_reason": data.get("done_reason", "stop"),
                            "eval_count": data.get("eval_count"),
                        }
                        return
        except error.URLError as exc:
            raise ConnectionError(f"Ollama server not reachable at {self.base_url}") from exc
        except TimeoutError as exc:
            raise TimeoutError("Ollama request timed out during generation") from exc
