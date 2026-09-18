"""Persistent, bounded self-improvement with fresh validation before promotion."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import copy
import fcntl
import json
from importlib.resources import files
import hashlib
import random
from pathlib import Path
import re
import statistics
import threading
import uuid

from .engine import DiscoveryAgent, online, world_summary
from .improve import improve
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .task import SumDifferenceTask
from .types import World, save_json, stable_seed
from .tasks.coding import CodingTask, validate_suite
from .sandbox import DockerSandbox
from .code_workflow import assess_selected, selected_source


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LabConfig:
    model: str = "qwen3.5:0.8b"
    task: str = "sum_difference"
    seed: int = 2027
    branches: int = 4
    depth: int = 4
    workers: int = 2
    revisions: int = 4
    validation_pairs: int = 4

    @property
    def budget(self):
        return self.branches * self.depth

    def validate(self):
        if self.task not in ("sum_difference", "python_code"):
            raise ValueError("Choose math or Python code as the task")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 120:
            raise ValueError("Choose an installed model.")
        for field, lo, hi in (("seed", 0, 2**31-1), ("branches", 2, 8), ("depth", 2, 8),
                              ("workers", 1, 4), ("revisions", 1, 8), ("validation_pairs", 2, 8)):
            value = getattr(self, field)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{field} must be an integer between {lo} and {hi}.")
        if self.budget > 32:
            raise ValueError("Use at most 32 attempts per episode in the local lab.")


def promotion_check(pairs: list[dict], required_pairs: int) -> dict:
    """Quality first; never trade a quality loss for a cheaper request count."""
    if len(pairs) != required_pairs or required_pairs < 2:
        return {"accepted": False, "reason": "Fresh validation is incomplete."}
    differences = [p["candidate"]["best"] - p["incumbent"]["best"] for p in pairs]
    old_work = sum(p["incumbent"]["calls"] for p in pairs)
    new_work = sum(p["candidate"]["calls"] for p in pairs)
    valid = all(p["candidate"]["valid_attempts"] > 0 for p in pairs)
    quality_ok = all(d >= -1e-12 for d in differences)
    improved = new_work < old_work or statistics.mean(differences) > 1e-12
    accepted = valid and quality_ok and improved
    if not valid:
        reason = "Candidate did not produce a valid construction in every fresh pair. Current policy kept."
    elif not quality_ok:
        reason = "Candidate lost solution quality on fresh data. Current policy kept."
    elif not improved:
        reason = "Candidate matched the current policy without improving quality or reducing work. Current policy kept."
    else:
        reason = "Candidate preserved quality on every fresh pair and improved quality or reduced work."
    return {"accepted": accepted, "reason": reason, "pairs": len(pairs), "quality_ok": quality_ok,
            "mean_quality_difference": statistics.mean(differences), "incumbent_calls": old_work,
            "candidate_calls": new_work, "call_savings_percent": 100 * (1 - new_work / old_work) if old_work else 0,
            "quality_losses": sum(d < -1e-12 for d in differences)}


class Paused(Exception):
    pass


class LabManager:
    """One local worker; durable stage boundaries; no scheduled or unbounded jobs."""
    def __init__(self, root: Path, base_url="http://localhost:11434", model_factory=OllamaModel):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url, self.model_factory = base_url, model_factory
        self._lock = threading.RLock()
        self._process_lock = (self.root / "server.lock").open("a+")
        try:
            fcntl.flock(self._process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._process_lock.close()
            raise RuntimeError("This lab already has a running server. Open that window instead.")
        self._states = {}
        self._thread = None
        self._active_id = None
        self._pause = threading.Event()
        for path in (self.root / "sessions").glob("*/state.json"):
            state = json.loads(path.read_text())
            if state["status"] in ("running", "pausing"):
                state["status"] = "interrupted"
                state["message"] = "The server stopped. Resume to continue from the last completed step."
                save_json(path, state)
            self._states[state["id"]] = state

    def close(self):
        self._pause.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=150)
        if self._thread and self._thread.is_alive():
            raise RuntimeError("A model request is still finishing; the lab lock remains held.")
        fcntl.flock(self._process_lock, fcntl.LOCK_UN)
        self._process_lock.close()

    def _directory(self, session_id):
        if not re.fullmatch(r"[a-f0-9]{12}", session_id) or session_id not in self._states:
            raise KeyError("Workspace not found.")
        return self.root / "sessions" / session_id

    def _save(self, state):
        state["updated_at"] = now()
        save_json(self._directory(state["id"]) / "state.json", state)

    def _event(self, state, message, **updates):
        with self._lock:
            state.update(updates)
            state["message"] = message
            state["events"].append({"time": now(), "message": message})
            state["events"] = state["events"][-160:]
            self._save(state)

    def create(self, name: str, config: LabConfig, suite: dict | None = None) -> dict:
        config.validate()
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Give the workspace a name of 1–80 characters.")
        if config.task == "python_code":
            suite = validate_suite(suite if suite is not None else json.loads(files("dream_rsi").joinpath("data/code-workflows.json").read_text()))
            if not any(p["split"] == "train" for p in suite["problems"]):
                raise ValueError("The code suite needs training problems")
            if sum(p["split"] == "validation" for p in suite["problems"]) < config.validation_pairs:
                raise ValueError("The suite needs at least one distinct validation problem per fresh pair")
        elif suite is not None:
            raise ValueError("Custom code suites require a Python workspace")
        sid = uuid.uuid4().hex[:12]
        policy = PolicySpec()
        state = {"id": sid, "name": name.strip(), "config": asdict(config), "created_at": now(), "updated_at": now(),
                 "status": "idle", "message": "Ready to collect its first experiments.", "events": [], "history": [],
                 "cycles": [], "active_cycle": None, "next_cycle": 1, "champion": {"version": 0, "policy": policy.to_dict()},
                 "versions": [{"version": 0, "policy": policy.to_dict(), "created_at": now(), "source": "Initial fixed exploration", "evidence": None}],
                 "task_metadata": None, "model_metadata": None, "usage": {"calls": 0, "discovery_calls": 0, "policy_calls": 0, "input_tokens": 0, "output_tokens": 0},
                 "best_artifact": None, "progress": None}
        with self._lock:
            self._states[sid] = state
            if suite is not None:
                save_json(self._directory(sid) / "code_suite.json", suite)
                state["task_metadata"] = {"suite_digest": hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest(), "runtime": None}
            self._save(state)
            save_json(self._directory(sid) / "versions" / "v0000.json", state["champion"])
        return self.get(sid)

    def list(self):
        with self._lock:
            return [{k: copy.deepcopy(s[k]) for k in ("id", "name", "created_at", "updated_at", "status", "message", "usage", "champion")}
                    for s in sorted(self._states.values(), key=lambda s: s["created_at"], reverse=True)]

    def get(self, session_id):
        with self._lock:
            self._directory(session_id)
            result = copy.deepcopy(self._states[session_id])
            result["policy_source"] = PolicySpec(**result["champion"]["policy"]).source()
            return result

    def world(self, session_id, relative):
        directory = self._directory(session_id)
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory) or path.name not in ("world.json", "partial_world.json"):
            raise ValueError("Invalid discovery tree.")
        return json.loads(path.read_text())

    def start(self, session_id, cycles=1, max_calls=240):
        if type(cycles) is not int or not 1 <= cycles <= 20 or type(max_calls) is not int or not 16 <= max_calls <= 2000:
            raise ValueError("Choose 1–20 cycles and a model-call limit between 16 and 2000.")
        with self._lock:
            self._directory(session_id)
            if self._thread and self._thread.is_alive():
                raise ValueError("Another improvement run is active. Pause it before starting a new one.")
            state = self._states[session_id]
            self._pause.clear()
            self._active_id = session_id
            self._event(state, "Checking the local model…", status="running", error=None,
                        run_control={"cycles_requested": cycles, "cycles_remaining": cycles, "max_new_calls": max_calls,
                                     "starting_calls": state["usage"]["calls"]})
            self._thread = threading.Thread(target=self._work, args=(state, cycles, max_calls), daemon=False, name="dream-rsi-lab")
            self._thread.start()
            return self.get(session_id)

    def pause(self, session_id):
        with self._lock:
            self._directory(session_id)
            state = self._states[session_id]
            if session_id != self._active_id or not self._thread or not self._thread.is_alive():
                return self.get(session_id)
            self._pause.set()
            self._event(state, "Pause requested. Finishing the current step and saving its evidence…", status="pausing")
            return self.get(session_id)

    def restore(self, session_id, version):
        with self._lock:
            state = self._states[session_id]
            if state["status"] in ("running", "pausing"):
                raise ValueError("Pause the workspace before restoring a policy.")
            if state["active_cycle"]:
                raise ValueError("Finish or discard the pending cycle before restoring a policy.")
            match = next((v for v in state["versions"] if v["version"] == version), None)
            if match is None:
                raise ValueError("Policy version not found.")
            state["champion"] = {"version": match["version"], "policy": match["policy"]}
            self._event(state, f"Restored policy v{version:02d}. All experiment history was retained.", status="idle")
            return self.get(session_id)

    def discard_pending(self, session_id):
        with self._lock:
            state = self._states[session_id]
            if state["status"] in ("running", "pausing"):
                raise ValueError("Pause before discarding a pending cycle.")
            cycle = state["active_cycle"]
            if cycle:
                cycle["outcome"] = "discarded"
                cycle["reason"] = "Discarded by user. Evidence retained; current policy unchanged."
                state["cycles"].append(cycle)
                state["active_cycle"] = None
            self._event(state, "Pending cycle discarded. Saved evidence remains available.", status="idle")
            return self.get(session_id)

    def _usage(self, state, model):
        usage = model.usage()
        with self._lock:
            state["usage"] = {"calls": sum(u["calls"] for u in usage.values()),
                              "discovery_calls": usage["discovery"]["calls"], "policy_calls": usage["policy"]["calls"],
                              "input_tokens": sum(u["input_tokens"] for u in usage.values()),
                              "output_tokens": sum(u["output_tokens"] for u in usage.values())}
            self._save(state)

    def _boundary(self, state, model, required, call_limit):
        self._usage(state, model)
        if self._pause.is_set():
            raise Paused("Paused. Resume will continue after the last completed step.")
        if state["usage"]["calls"] + required > call_limit:
            raise Paused("Call limit reached: not enough budget for the next complete step. Resume with a new allowance.")

    def _load_worlds(self, state):
        directory = self._directory(state["id"])
        return [World.from_dict(json.loads((directory / relative).read_text())) for relative in state["history"]]

    def _record_artifact(self, state, world):
        if world.task_name == "python_code":
            source, score, node_id = selected_source(world)
            with self._lock:
                previous = state["best_artifact"]
                if previous is None or score > previous["score"]:
                    state["best_artifact"] = {"score": score, "points": [], "source": source, "artifact": source,
                                              "diagnostics": {"visible_score": score}, "world": world.name,
                                              "node": node_id or "baseline", "rationale": "Selected on visible tests only",
                                              "task": world.task_name, "case_id": world.case_id}
                    self._save(state)
            return
        valid = [n for n in world.nodes if n.evaluation.valid]
        if not valid:
            return
        best = max(valid, key=lambda n: n.evaluation.score)
        with self._lock:
            previous = state["best_artifact"]
            if previous is None or best.evaluation.score > previous["score"]:
                state["best_artifact"] = {"score": best.evaluation.score, "points": list(best.points), "source": best.source,
                                          "diagnostics": best.evaluation.diagnostics, "world": world.name, "node": best.id,
                                          "rationale": best.rationale, "artifact": best.artifact, "task": world.task_name, "case_id": world.case_id}
                self._save(state)

    def _episode(self, state, cycle, key, spec, seed, history, model, limit):
        directory = self._directory(state["id"])
        existing = cycle["worlds"].get(key)
        if existing:
            return World.from_dict(json.loads((directory / existing).read_text()))
        cfg = LabConfig(**state["config"])
        self._boundary(state, model, cfg.budget, limit)
        with self._lock:
            attempt = cycle["attempts"].get(key, 0) + 1
            cycle["attempts"][key] = attempt
            self._save(state)
        name = f"cycle-{cycle['index']:04d}-{key}-try-{attempt:02d}"
        policy = Policy(spec)
        planning = [world_summary(w) for w in history]
        plan = policy.plan_grid(cfg.branches, cfg.depth, cfg.workers, planning)
        def progress(data):
            self._usage(state, model)
            with self._lock:
                state["progress"] = {**data, "stage": key, "attempt_cap": cfg.budget}
                self._save(state)
        task = SumDifferenceTask()
        if cfg.task == "python_code":
            suite = json.loads((directory / "code_suite.json").read_text())
            if key == "live":
                task = CodingTask(suite, "train", self._sandbox)
            else:
                pair_index = int(key.split("-")[1])
                task = CodingTask(suite, "validation", self._sandbox, cycle["validation_problems"][pair_index])
        world, _ = online(policy, DiscoveryAgent(model, task), name, seed, *plan, cfg.workers, cfg.budget,
                          history[-8:], directory / "worlds" / name, (cfg.branches, cfg.depth), on_progress=progress, planning_history=planning)
        with self._lock:
            cycle["worlds"][key] = f"worlds/{name}/world.json"
            self._save(state)
        self._record_artifact(state, world)
        return world

    def _assess(self, state, cycle, key, world):
        if world.task_name == "sum_difference":
            return {**world_summary(world), "valid_attempts": sum(n.evaluation.valid for n in world.nodes)}
        directory = self._directory(state["id"])
        path = directory / "assessments" / f"cycle-{cycle['index']:04d}-{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        suite = json.loads((directory / "code_suite.json").read_text())
        task = CodingTask(suite, "validation", self._sandbox, world.case_id)
        selected = assess_selected(task, world)
        result = {**world_summary(world), "case_id": world.case_id, "visible_best": selected["visible_score"],
                  "best": selected["hidden_score"], "valid_attempts": int(selected["hidden_valid"] and selected["hidden_score"] > 0),
                  "selected_node": selected["node"], "assessment": selected["assessment"]}
        save_json(path, result)
        return result

    def _work(self, state, cycles, max_calls):
        model = None
        try:
            cfg = LabConfig(**state["config"])
            directory = self._directory(state["id"])
            if cfg.task == "python_code":
                suite = validate_suite(json.loads((directory / "code_suite.json").read_text()))
                digest = hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest()
                if digest != state["task_metadata"]["suite_digest"]:
                    raise ValueError("Code suite changed. Create a new workspace for a different suite.")
                self._sandbox = DockerSandbox()
                runtime = self._sandbox.inspect()
                previous = state["task_metadata"]["runtime"]
                if previous and previous != runtime:
                    raise ValueError("Sandbox image changed. Create a new workspace to keep evaluation reproducible.")
                with self._lock:
                    state["task_metadata"]["runtime"] = runtime
                    self._save(state)
            model = self.model_factory(cfg.model, directory / "model_calls", self.base_url)
            # Rehydrate physical-call accounting; completed requests are never
            # issued again just because the application was restarted.
            model.records = [json.loads(p.read_text()) for p in sorted((directory / "model_calls").glob("*.json"))]
            metadata = model.inspect()
            with self._lock:
                if state["model_metadata"] and state["model_metadata"]["digest"] != metadata["digest"]:
                    raise ValueError("The model changed. Create a new workspace to keep comparisons meaningful.")
                state["model_metadata"] = metadata
                self._save(state)
            self._usage(state, model)
            with self._lock:
                state["run_control"]["starting_calls"] = state["usage"]["calls"]
                self._save(state)
            limit = state["usage"]["calls"] + max_calls
            for _ in range(cycles):
                self._boundary(state, model, 0, limit)
                with self._lock:
                    if state["active_cycle"] is None:
                        index = state["next_cycle"]
                        state["next_cycle"] += 1
                        state["active_cycle"] = {"index": index, "started_at": now(), "phase": "discover", "attempts": {},
                                                 "worlds": {}, "pairs": [], "incumbent": copy.deepcopy(state["champion"]),
                                                 "validation_seeds": [stable_seed(cfg.seed, state["id"], "validation", index, i) for i in range(cfg.validation_pairs)]}
                        if cfg.task == "python_code":
                            pool = [p["id"] for p in suite["problems"] if p["split"] == "validation"]
                            state["active_cycle"]["validation_problems"] = random.Random(stable_seed(cfg.seed, state["id"], index, "problems")).sample(pool, cfg.validation_pairs)
                        self._save(state)
                    cycle = state["active_cycle"]
                incumbent = PolicySpec(**cycle["incumbent"]["policy"])
                history = self._load_worlds(state)
                if cycle["phase"] == "discover":
                    self._event(state, f"Cycle {cycle['index']}: collecting experiments with policy v{cycle['incumbent']['version']:02d}.")
                    world = self._episode(state, cycle, "live", incumbent, stable_seed(cfg.seed, state["id"], "live", cycle["index"]), history, model, limit)
                    with self._lock:
                        path = cycle["worlds"]["live"]
                        if path not in state["history"]:
                            state["history"].append(path)
                        cycle["live"] = world_summary(world)
                        cycle["phase"] = "dream"
                        self._save(state)
                    history = self._load_worlds(state)
                if cycle["phase"] == "dream":
                    self._boundary(state, model, cfg.revisions, limit)
                    self._event(state, f"Cycle {cycle['index']}: proposing and replaying {cfg.revisions} controller edits.")
                    pool = []
                    for world in history[-12:]:
                        width, depth = Policy(incumbent).plan_grid(cfg.branches, cfg.depth, cfg.workers, world.planning_history or [])
                        if width <= world.branch_count and depth <= world.max_depth:
                            pool.append(world)
                    if not pool:
                        raise ValueError("No completed discovery tree supports the current policy.")
                    attempt = cycle["attempts"].get("dream", 0) + 1
                    with self._lock:
                        cycle["attempts"]["dream"] = attempt
                        self._save(state)
                    folder = directory / "candidates" / f"cycle-{cycle['index']:04d}-try-{attempt:02d}"
                    feedback = json.dumps([{
                        "reason": c.get("reason", ""), "gate": c.get("gate"),
                        "proposed_policy": c.get("candidate")
                    } for c in state["cycles"][-3:]])
                    def policy_progress(data):
                        self._usage(state, model)
                        with self._lock:
                            state["progress"] = {"stage": "dream", **data}
                            self._save(state)
                    candidate, selection = improve(model, incumbent, pool, cfg.revisions, cfg.budget, .001, .0005,
                                                    stable_seed(cfg.seed, state["id"], cycle["index"], attempt), folder,
                                                    editor="focused", feedback=feedback, on_progress=policy_progress)
                    with self._lock:
                        cycle["candidate"] = candidate.to_dict()
                        cycle["selection"] = selection
                        cycle["replay_worlds"] = [w.name for w in pool]
                        cycle["candidate_folder"] = str(folder.relative_to(directory))
                        cycle["phase"] = "validate" if selection["after"] > selection["before"] + 1e-12 else "decide"
                        self._save(state)
                if cycle["phase"] == "validate":
                    candidate = PolicySpec(**cycle["candidate"])
                    for i, seed in enumerate(cycle["validation_seeds"]):
                        if i < len(cycle["pairs"]):
                            continue
                        pair = {"seed": seed}
                        for arm in (("candidate", "incumbent") if i % 2 == 0 else ("incumbent", "candidate")):
                            self._event(state, f"Cycle {cycle['index']}: fresh check {i+1}/{cfg.validation_pairs} · {arm}.")
                            spec = candidate if arm == "candidate" else incumbent
                            world = self._episode(state, cycle, f"check-{i:02d}-{arm}", spec, seed, history, model, limit)
                            pair[arm] = self._assess(state, cycle, f"check-{i:02d}-{arm}", world)
                        with self._lock:
                            cycle["pairs"].append(pair)
                            self._save(state)
                    with self._lock:
                        cycle["phase"] = "decide"
                        self._save(state)
                # A stop request cannot accidentally promote a half-validated
                # candidate. Resume commits only after this explicit boundary.
                self._boundary(state, model, 0, limit)
                with self._lock:
                    if cycle["pairs"]:
                        decision = promotion_check(cycle["pairs"], cfg.validation_pairs)
                        cycle["gate"] = decision
                        cycle["outcome"] = "promoted" if decision["accepted"] else "rejected"
                        cycle["reason"] = decision["reason"]
                        if decision["accepted"]:
                            version = max(v["version"] for v in state["versions"]) + 1
                            entry = {"version": version, "policy": cycle["candidate"], "created_at": now(),
                                     "source": f"Cycle {cycle['index']}: fresh validation passed", "evidence": decision}
                            save_json(directory / "versions" / f"v{version:04d}.json", entry)
                            state["versions"].append(entry)
                            state["champion"] = {"version": version, "policy": cycle["candidate"]}
                    else:
                        cycle["outcome"] = "unchanged"
                        cycle["reason"] = "No edit improved replay. Current policy kept; unnecessary validation calls were avoided."
                    cycle["finished_at"] = now()
                    state["cycles"].append(copy.deepcopy(cycle))
                    state["active_cycle"] = None
                    state["progress"] = None
                    state["run_control"]["cycles_remaining"] -= 1
                    self._event(state, f"Cycle {cycle['index']} · {cycle['outcome']}. {cycle['reason']}")
            self._event(state, "Run complete. Current policy and all evidence are saved.", status="idle")
        except Paused as exc:
            self._event(state, str(exc), status="paused", progress=None)
        except Exception as exc:
            self._event(state, f"Stopped: {exc}", status="failed", error=str(exc), progress=None)
        finally:
            if model is not None:
                self._usage(state, model)
            with self._lock:
                self._active_id = None
