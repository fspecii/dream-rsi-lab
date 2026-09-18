"""Disposable, resource-limited Docker execution. No host-code execution fallback.

Expected answers stay in the parent process. Containers receive source and function
inputs only, so a generated program cannot forge a passing-test count. Containers
are isolation for local experiments, not a security boundary for a hostile service.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import subprocess
import threading
import time
import uuid


class SandboxUnavailable(RuntimeError):
    pass


# Results use a saved output stream; ordinary print calls are kept out of protocol.
# No expected answers or private test labels are sent to this driver.
DRIVER = r'''
import contextlib, io, json, sys
request = json.load(sys.stdin)
output = sys.stdout
results = []
namespace = {"__name__": "candidate"}
class Sink(io.TextIOBase):
    def write(self, value): return len(value)
try:
    with contextlib.redirect_stdout(Sink()), contextlib.redirect_stderr(Sink()):
        exec(compile(request["source"], "candidate.py", "exec"), namespace)
    fn = namespace[request["entrypoint"]]
    for case in request["inputs"]:
        try:
            with contextlib.redirect_stdout(Sink()), contextlib.redirect_stderr(Sink()):
                value = fn(*case.get("args", []), **case.get("kwargs", {}))
            # Round-trip now, before later calls can mutate a returned object.
            value = json.loads(json.dumps(value, allow_nan=False))
            results.append({"ok": True, "value": value})
        except BaseException as exc:
            results.append({"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:300]})
except BaseException as exc:
    results = [{"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:300]} for _ in request["inputs"]]
output.write(json.dumps({"results": results}, allow_nan=False))
'''


@dataclass(frozen=True)
class TestResult:
    passed: int
    total: int
    cases: list[dict]
    status: str
    seconds: float
    image: str

    @property
    def score(self):
        return self.passed / self.total if self.total else 0.0


def equivalent(actual, expected):
    """JSON structural equality; booleans never count as numeric answers."""
    if type(actual) is bool or type(expected) is bool:
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return (not isinstance(actual, float) or math.isfinite(actual)) and (not isinstance(expected, float) or math.isfinite(expected)) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(equivalent(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(equivalent(a, b) for a, b in zip(actual, expected))
    return actual == expected


class DockerSandbox:
    def __init__(self, image="python:3.12-slim", timeout=10, output_limit=65536):
        if not 1 <= timeout <= 120 or not 1024 <= output_limit <= 1048576:
            raise ValueError("Invalid sandbox limits")
        self.image, self.timeout, self.output_limit = image, timeout, output_limit
        self._image_id = None
        self._lock = threading.Lock()

    def inspect(self):
        with self._lock:
            if self._image_id:
                return {"runtime": "docker", "image": self._image_id}
            try:
                check = subprocess.run(["docker", "image", "inspect", self.image, "--format", "{{.Id}}"],
                                       capture_output=True, text=True, timeout=8)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SandboxUnavailable("Docker is unavailable. Start Docker or Colima before running code tasks.") from exc
            if check.returncode or not check.stdout.strip().startswith("sha256:"):
                raise SandboxUnavailable(f"Sandbox image unavailable. Start Docker and run: docker pull {self.image}")
            self._image_id = check.stdout.strip()
            return {"runtime": "docker", "image": self._image_id}

    def command(self, name, image):
        return ["docker", "run", "--rm", "--pull=never", "--name", name, "--network=none", "--read-only",
                "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=32",
                "--memory=256m", "--memory-swap=256m", "--cpus=1", "--ulimit", "nofile=64:64",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--log-driver=none", "-i", image,
                "python", "-I", "-B", "-c", DRIVER]

    def run(self, source: str, entrypoint: str, cases: list[dict]) -> TestResult:
        if not isinstance(source, str) or not source.strip() or len(source.encode()) > 32768:
            raise ValueError("Candidate source must contain 1–32768 bytes")
        if not isinstance(entrypoint, str) or not entrypoint.isidentifier() or entrypoint.startswith("_"):
            raise ValueError("Entrypoint must be a public Python function name")
        if not isinstance(cases, list) or not 1 <= len(cases) <= 128:
            raise ValueError("Provide 1–128 test cases")
        for case in cases:
            if not isinstance(case, dict) or "expected" not in case or not isinstance(case.get("args", []), list) or not isinstance(case.get("kwargs", {}), dict):
                raise ValueError("Tests need args (list), kwargs (object), and expected")
        image = self.inspect()["image"]
        payload = json.dumps({"source": source, "entrypoint": entrypoint,
                              "inputs": [{"args": c.get("args", []), "kwargs": c.get("kwargs", {})} for c in cases]}, allow_nan=False).encode()
        if len(payload) > 262144:
            raise ValueError("Source and test inputs exceed 256 KiB")
        name = "dream-rsi-" + uuid.uuid4().hex
        started = time.monotonic()
        output, errors = bytearray(), bytearray()
        overflow = threading.Event()
        process = subprocess.Popen(self.command(name, image), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def drain(stream, target):
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                remaining = self.output_limit - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    process.kill()
                    break
        def send():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        threads = [threading.Thread(target=drain, args=(process.stdout, output), daemon=True),
                   threading.Thread(target=drain, args=(process.stderr, errors), daemon=True),
                   threading.Thread(target=send, daemon=True)]
        status = "completed"
        try:
            for thread in threads:
                thread.start()
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                status = "timeout"
                process.kill()
                process.wait(timeout=3)
        finally:
            # Killing the CLI alone would leave its container running.
            try:
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SandboxUnavailable(f"Could not confirm sandbox cleanup for {name}.") from exc
            for thread in threads:
                thread.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
        if overflow.is_set():
            status = "output_limit"
        if status == "completed" and process.returncode == 125:
            raise SandboxUnavailable("Docker could not start the isolated runner: " + errors.decode(errors="replace")[:400])
        try:
            rows = json.loads(output)["results"] if status == "completed" and process.returncode == 0 else []
            if not isinstance(rows, list) or len(rows) != len(cases):
                raise ValueError("wrong result count")
        except (ValueError, KeyError, TypeError, RecursionError):
            rows = []
            if status == "completed":
                status = "execution_error"
        checked = []
        for i, case in enumerate(cases):
            row = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
            try:
                passed = row.get("ok") is True and "value" in row and equivalent(row["value"], case["expected"])
            except (RecursionError, OverflowError):
                passed = False
            checked.append({"index": i, "passed": passed, "actual": row.get("value"),
                            "error": str(row.get("error", "" if passed else status if status != "completed" else "wrong output"))[:400]})
        return TestResult(sum(c["passed"] for c in checked), len(cases), checked, status, time.monotonic()-started, image)
