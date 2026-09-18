"""Ollama transport with immutable request/response logs and explicit cost accounting."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

from .types import save_json


class OllamaModel:
    def __init__(self, model: str, log_dir: Path, base_url: str = "http://localhost:11434", timeout: float = 120):
        self.model, self.log_dir, self.base_url, self.timeout = model, log_dir, base_url.rstrip("/"), timeout
        self._lock = threading.Lock()
        self.records: list[dict] = []

    def inspect(self) -> dict:
        with urllib.request.urlopen(self.base_url + "/api/tags", timeout=5) as response:
            models = json.load(response)["models"]
        matching = [m for m in models if m["name"] == self.model or m["name"] == self.model + ":latest"]
        if not matching:
            raise RuntimeError(f"Model {self.model!r} not installed in Ollama; available: {[m['name'] for m in models]}")
        return matching[0]

    def generate(self, prompt: str, schema: dict, seed: int, role: str, call_id: str, max_tokens: int = 600) -> dict:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "think": False, "format": schema, "keep_alive": "15m",
                   "options": {"seed": seed, "temperature": 0.7, "num_ctx": 32768, "num_predict": max_tokens}}
        started = time.monotonic()
        record = {"id": call_id, "role": role, "request": payload}
        try:
            request = urllib.request.Request(self.base_url + "/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.load(response)
            record["response"] = raw
            if raw.get("done_reason") == "length":
                raise ValueError("model response truncated by token limit")
            result = json.loads(raw["message"]["content"])
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")
            return result
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record["error"] = str(exc)
            # Infrastructure failure is fatal, not a low-scoring discovery.
            raise RuntimeError(f"Ollama request failed ({call_id}): {exc}") from exc
        except (ValueError, KeyError) as exc:
            record["error"] = str(exc)
            raise ValueError(f"Invalid model response ({call_id}): {exc}") from exc
        finally:
            record["wall_seconds"] = time.monotonic() - started
            with self._lock:
                save_json(self.log_dir / f"{call_id}.json", record)
                self.records.append(record)

    def usage(self) -> dict:
        result = {}
        for role in ("discovery", "policy"):
            rows = [r for r in self.records if r["role"] == role]
            result[role] = {"calls": len(rows), "input_tokens": sum(r.get("response", {}).get("prompt_eval_count", 0) for r in rows),
                            "output_tokens": sum(r.get("response", {}).get("eval_count", 0) for r in rows),
                            "request_seconds": sum(r["wall_seconds"] for r in rows), "errors": sum("error" in r for r in rows)}
        return result
