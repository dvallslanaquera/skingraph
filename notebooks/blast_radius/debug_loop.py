"""Agentic debugging-loop benchmark: Opus 4.8 vs GLM-5.2 on a real bug-fix.

Unlike the single-shot ``runner`` (hand the model the whole repo, score a one-shot
answer against a grep oracle), this benchmark gives each model *tools* and lets it
iterate to fix a real bug, scored by a real failing test.

Scenario — commit ``d11ae62`` ("fix: solved problem with the backend when processing
the images"):

  * Bug: ``POST /scan`` ran the whole LangGraph pipeline in one blocking request; on
    Railway the long idle connection tripped the reverse-proxy timeout and the browser
    reported a generic "backend not running" error.
  * Fix: added a streaming ``POST /scan/stream`` SSE endpoint that emits frames as each
    node finishes, with keepalive pings.
  * Oracle: ``d11ae62`` *also* added the ``test_scan_stream_*`` tests (fully offline,
    graph stubbed). We check out the buggy parent ``d11ae62^``, apply only the test
    patch from ``d11ae62``, and let the model edit source until those tests pass — the
    SWE-bench pattern.

Run via the repo entry point::

    python run_benchmark.py --debug-loop                # both models
    python run_benchmark.py --debug-loop --models opus-4-8 --steps 15

Results are written to ``results/debug_loop_<timestamp>.json`` (+ ``debug_loop_latest.json``)
and NEVER touch ``results/latest.json`` (the single-shot benchmark's file).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, models


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """subprocess.run that always decodes as UTF-8.

    On Windows the default text codec is the locale code page (cp932 on a Japanese
    install), which blows up on the repo's UTF-8 source (the fake coach state in
    tests/test_api.py contains Japanese). Forcing UTF-8 + replace keeps every tool,
    verdict, and git call byte-safe across platforms.
    """
    kw.setdefault("capture_output", True)
    return subprocess.run(cmd, encoding="utf-8", errors="replace", **kw)


# --- Scenario constants ----------------------------------------------------
FIX_COMMIT = "d11ae62"
PARENT_COMMIT = "d11ae62^"          # resolved by git at run time
TEST_PATCH_PATH = "tests/test_api.py"   # the only test file touched by the fix
SOURCE_FILES = ("src/api/main.py", "src/api/service.py")  # where the fix lives
VERDICT_TARGET = "scan_stream"      # pytest -k expression that defines "done"
REGRESSION_TARGET = "tests/test_api.py"  # full file — must not regress

DEFAULT_STEPS = 15
RUN_TESTS_TIMEOUT = 180            # seconds


# --- Prompts (identical for every model) ------------------------------------
SYSTEM_PROMPT = (
    "You are an autonomous software engineer working in a Python FastAPI + LangGraph "
    "repository. You debug and fix a backend bug by inspecting code, editing files, and "
    "running the test suite. You ACT by calling tools. When you have nothing more to do, "
    "respond with a short plain-text summary and NO tool calls to finish. Always verify "
    "your fix with `run_tests` (target `scan_stream`) before finishing."
)

USER_PROMPT = """\
A bug is reported in this backend (FastAPI + LangGraph).

Symptom: on the deployed host, `POST /scan` runs the entire LangGraph pipeline in a \
single blocking request. The connection sits idle for tens of seconds during the slow \
coach/VLM step, exceeds the platform reverse-proxy timeout, and is dropped — so the \
browser reports a generic "backend not running" network error even though the server is \
healthy. The fix is to add a streaming endpoint so bytes flow continuously (no idle \
proxy timeout) and the client gets per-stage progress. The existing `/scan` endpoint \
must keep working unchanged.

"Done" is defined by tests: `tests/test_api.py` contains new `test_scan_stream_*` tests \
(an SSE endpoint) that currently FAIL. Read that test file to learn the exact contract, \
implement the endpoint, and use `run_tests` (target `scan_stream`) to confirm the \
`scan_stream` tests pass and the rest of `tests/test_api.py` does not regress.

Starting point: `/scan` and `run_scan` live in `src/api/main.py` and `src/api/service.py`. \
The LangGraph graph object is `graph_app` in `src/api/service.py` and supports both \
`.invoke(inputs, config)` and `.stream(inputs, config, stream_mode=[...])`.

Current failing test output (the symptom):
```
{symptom}
```

Begin. Call tools to explore and edit; once the targeted tests pass, finish with a \
plain-text summary and no tool calls."""


# --- Tool surface (provider-neutral, OpenAI-shaped; mapped per provider) ----
# Flat argument schemas only — nested objects get stringified by some GLM/Ollama paths.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List tracked files under a worktree-relative directory (default: repo root). Returns POSIX paths, one per line.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "worktree-relative dir or file path; default '.'"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a worktree-relative file with 1-based line numbers. Optional start/end line range (inclusive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "worktree-relative file path"},
                    "start": {"type": "integer", "description": "first line to show (1-based, default 1)"},
                    "end": {"type": "integer", "description": "last line to show (inclusive, default end of file)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search tracked files for lines matching a Python regular expression. Returns 'file:line: text' hits (capped at 200).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regex"},
                    "glob": {"type": "string", "description": "file glob filter, default '*.py'"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exactly one occurrence of `old_string` with `new_string` in a worktree-relative file. Fails if old_string is absent or appears more than once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "worktree-relative file path"},
                    "old_string": {"type": "string", "description": "exact text to replace (must be unique in the file)"},
                    "new_string": {"type": "string", "description": "replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run pytest in the worktree. target='scan_stream' runs the scan_stream tests (the done-criterion); target='full' runs all of tests/test_api.py (regression check). Returns exit code + truncated output.",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string", "description": "'scan_stream' (default) or 'full'"}},
                "required": [],
            },
        },
    },
]


# --- Tool harness -----------------------------------------------------------
class ToolHarness:
    """Executes the five tools against a worktree path and records call counts."""

    READ_CAP_LINES = 4000
    READ_CAP_CHARS = 60000
    GREP_CAP = 200

    def __init__(self, worktree: Path, venv_python: str):
        self.root = worktree
        self.venv_python = venv_python
        self.calls: dict[str, int] = {t["function"]["name"]: 0 for t in TOOLS}
        self.n_edits = 0
        self.run_tests_results: list[dict] = []

    # path safety: keep inside the worktree
    def _resolve(self, rel: str) -> Path:
        rel = (rel or ".").strip().strip("`'\"")
        rel = rel.replace("\\", "/")
        rel = re.sub(r"^\./+", "", rel)
        p = (self.root / rel).resolve() if rel not in ("", ".") else self.root.resolve()
        try:
            p.relative_to(self.root.resolve())
        except ValueError:
            raise ValueError(f"path escapes worktree: {rel!r}")
        return p

    def _tracked_files(self, path_filter: str = "") -> list[str]:
        out = _run(
            ["git", "ls-files", path_filter] if path_filter else ["git", "ls-files"],
            cwd=self.root, check=True,
        )
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]

    def list_dir(self, args: dict) -> str:
        path = args.get("path", ".") or "."
        if path in (".", "", "./"):
            files = self._tracked_files()
        else:
            p = self._resolve(path)
            rel = p.relative_to(self.root).as_posix()
            files = self._tracked_files(rel)
            if not files and p.is_file():
                return f"{path} (single file)"
        if not files:
            return f"(no tracked files under {path!r})"
        return "\n".join(files) if len(files) <= 400 else "\n".join(files[:400]) + f"\n... ({len(files) - 400} more)"

    def read_file(self, args: dict) -> str:
        path = args.get("path", "")
        p = self._resolve(path)
        if not p.is_file():
            return f"ERROR: not a file: {path!r}"
        start = args.get("start")
        end = args.get("end")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        s = max(1, int(start)) if start else 1
        e = min(len(lines), int(end)) if end else len(lines)
        body = []
        total = 0
        for i in range(s, e + 1):
            if total > self.READ_CAP_CHARS:
                body.append(f"... (truncated at {self.READ_CAP_CHARS} chars)")
                break
            body.append(f"{i:>5} | {lines[i - 1]}")
            total += len(body[-1])
            if len(body) > self.READ_CAP_LINES:
                body.append(f"... (truncated at {self.READ_CAP_LINES} lines; file has {len(lines)} total)")
                break
        return "\n".join(body)

    def grep(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        glob = args.get("glob", "*.py") or "*.py"
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: bad regex: {exc}"
        files = self._tracked_files(glob)
        hits: list[str] = []
        for rel in files:
            txt = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(txt.splitlines(), start=1):
                if rx.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(hits) >= self.GREP_CAP:
                        hits.append(f"... (capped at {self.GREP_CAP} hits)")
                        return "\n".join(hits)
        if not hits:
            return "(no matches)"
        return "\n".join(hits)

    def edit_file(self, args: dict) -> str:
        path = args.get("path", "")
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        if old == "":
            return "ERROR: old_string is empty"
        p = self._resolve(path)
        if not p.is_file():
            return f"ERROR: not a file: {path!r}"
        text = p.read_text(encoding="utf-8", errors="replace")
        n = text.count(old)
        if n == 0:
            return "ERROR: old_string not found"
        if n > 1:
            return f"ERROR: old_string matches {n} times; make it unique"
        new_text = text.replace(old, new, 1)
        p.write_text(new_text, encoding="utf-8")
        self.n_edits += 1
        # show a little context around the change
        idx = new_text.find(new)
        line_no = new_text.count("\n", 0, idx) + 1
        return f"OK: edited {path} at line {line_no} ({len(new)} chars inserted)"

    def run_tests(self, args: dict) -> str:
        target = (args.get("target") or "scan_stream").strip().lower()
        if target == "full":
            cmd = ["tests/test_api.py"]
        elif target == "scan_stream":
            cmd = ["tests/test_api.py", "-k", "scan_stream"]
        else:
            cmd = ["tests/test_api.py", "-k", target]
        argv = [self.venv_python, "-m", "pytest", *cmd, "-q", "--no-header",
                "-p", "no:cacheprovider", "--tb=short"]
        env = {**os.environ, "PYTHONPATH": str(self.root)}
        try:
            proc = _run(argv, cwd=self.root, env=env, timeout=RUN_TESTS_TIMEOUT)
            passed = proc.returncode == 0
        except subprocess.TimeoutExpired:
            self.run_tests_results.append({"target": target, "passed": False, "timeout": True})
            return f"TIMEOUT after {RUN_TESTS_TIMEOUT}s (target={target})"
        out = (proc.stdout or "") + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
        out = out if len(out) <= 6000 else out[-6000:]
        self.run_tests_results.append({"target": target, "passed": passed, "timeout": False})
        return f"EXIT={proc.returncode} ({'PASS' if passed else 'FAIL'}) target={target}\n{out}"

    def dispatch(self, name: str, args: dict) -> str:
        self.calls[name] = self.calls.get(name, 0) + 1
        try:
            if name == "list_dir":
                return self.list_dir(args or {})
            if name == "read_file":
                return self.read_file(args or {})
            if name == "grep":
                return self.grep(args or {})
            if name == "edit_file":
                return self.edit_file(args or {})
            if name == "run_tests":
                return self.run_tests(args or {})
            return f"ERROR: unknown tool {name!r}"
        except Exception as exc:  # noqa: BLE001 — never kill the loop over a tool
            return f"ERROR: {type(exc).__name__}: {exc}"


# --- Loop clients -----------------------------------------------------------
@dataclass
class StepResult:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # {id, name, input}
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""
    error: str | None = None
    truncated: bool = False
    latency: float = 0.0


class AnthropicLoop:
    """Claude Opus 4.8 with tool use."""

    def __init__(self, cfg: config.ModelConfig, task_prompt: str):
        import anthropic  # lazy
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=models.resolve_api_key(cfg), timeout=600.0)
        self.system = SYSTEM_PROMPT
        self.messages: list[dict] = [{"role": "user", "content": task_prompt}]
        self._tools = [
            {"name": t["function"]["name"],
             "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]}
            for t in TOOLS
        ]

    def step(self) -> StepResult:
        t0 = time.perf_counter()
        try:
            resp = self.client.messages.create(
                model=self.cfg.model_id,
                max_tokens=config.MAX_OUTPUT_TOKENS,
                system=self.system,
                messages=self.messages,
                tools=self._tools,
                tool_choice={"type": "auto"},
            )
        except Exception as exc:  # noqa: BLE001
            return StepResult(error=f"{type(exc).__name__}: {exc}")
        latency = time.perf_counter() - t0
        # append the raw assistant turn (preserves tool_use ids for threading)
        self.messages.append({"role": "assistant", "content": resp.content})
        tool_calls, text = [], []
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                tool_calls.append({"id": b.id, "name": b.name, "input": b.input or {}})
            elif getattr(b, "type", None) == "text":
                text.append(b.text)
        u = resp.usage
        usage = {
            "input": getattr(u, "input_tokens", 0),
            "output": getattr(u, "output_tokens", 0),
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_creation": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }
        return StepResult(
            text="\n".join(text), tool_calls=tool_calls, usage=usage,
            stop_reason=resp.stop_reason or "",
            truncated=(resp.stop_reason == "max_tokens"),
            latency=latency,
        )

    def feed(self, results: list[dict]) -> None:
        # results: [{id, name, result}]
        self.messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": r["id"], "content": r["result"]}
                        for r in results],
        })

    def cost(self, usage: dict) -> float:
        return models._anthropic_cost(self.cfg, _usage_to_model_result(usage))


class OpenAILoop:
    """GLM-5.2 via OpenAI-compatible function calling (z.ai / Zhipu)."""

    def __init__(self, cfg: config.ModelConfig, task_prompt: str):
        from openai import OpenAI  # lazy
        self.cfg = cfg
        self.client = OpenAI(api_key=models.resolve_api_key(cfg), base_url=cfg.base_url, timeout=600.0)
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]

    def step(self) -> StepResult:
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=self.cfg.model_id,
                max_tokens=config.MAX_OUTPUT_TOKENS,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as exc:  # noqa: BLE001
            return StepResult(error=f"{type(exc).__name__}: {exc}")
        latency = time.perf_counter() - t0
        msg = resp.choices[0].message
        finish = resp.choices[0].finish_reason
        # append the assistant turn verbatim (keeps tool_calls + their ids)
        assistant = {"role": "assistant", "content": msg.content or ""}
        tcs = msg.tool_calls or []
        if tcs:
            assistant["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ]
        self.messages.append(assistant)
        tool_calls = []
        for tc in tcs:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "input": args})
        u = resp.usage
        usage = {
            "input": getattr(u, "prompt_tokens", 0) if u else 0,
            "output": getattr(u, "completion_tokens", 0) if u else 0,
        }
        return StepResult(
            text=msg.content or "", tool_calls=tool_calls, usage=usage,
            stop_reason=finish or "", truncated=(finish == "length"),
            latency=latency,
        )

    def feed(self, results: list[dict]) -> None:
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r["id"], "content": r["result"]})

    def cost(self, usage: dict) -> float:
        return models._simple_cost(self.cfg, _usage_to_model_result(usage))


class OllamaLoop:
    """GLM-5.2 via Ollama (Cloud) tool calling."""

    def __init__(self, cfg: config.ModelConfig, task_prompt: str):
        import ollama  # lazy
        self.cfg = cfg
        key = models.resolve_api_key(cfg)
        host = cfg.base_url
        if key:
            auth = key if key.lower().startswith("bearer ") else f"Bearer {key}"
            self.client = ollama.Client(host=host or "https://ollama.com",
                                        headers={"Authorization": auth})
        elif host:
            self.client = ollama.Client(host=host)
        else:
            self.client = ollama.Client()
        self.num_ctx = config.OLLAMA_NUM_CTX
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]

    def step(self) -> StepResult:
        t0 = time.perf_counter()
        try:
            resp = self.client.chat(
                model=self.cfg.model_id, messages=self.messages,
                tools=TOOLS, options={"temperature": 0, "num_ctx": self.num_ctx},
            )
        except Exception as exc:  # noqa: BLE001
            return StepResult(error=f"{type(exc).__name__}: {exc}")
        latency = time.perf_counter() - t0
        m = resp.message
        tcs = m.tool_calls or []
        assistant = {"role": "assistant", "content": m.content or ""}
        if tcs:
            assistant["tool_calls"] = [
                {"function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in tcs
            ]
        self.messages.append(assistant)
        tool_calls = [
            {"id": f"{c.function.name}_{i}", "name": c.function.name,
             "input": c.function.arguments or {}}
            for i, c in enumerate(tcs)
        ]
        usage = {
            "input": getattr(resp, "prompt_eval_count", 0) or 0,
            "output": getattr(resp, "eval_count", 0) or 0,
        }
        return StepResult(
            text=m.content or "", tool_calls=tool_calls, usage=usage,
            stop_reason=("tool_calls" if tcs else "stop"),
            latency=latency,
        )

    def feed(self, results: list[dict]) -> None:
        for r in results:
            self.messages.append({"role": "tool", "tool_name": r["name"], "content": r["result"]})

    def cost(self, usage: dict) -> float:
        return models._simple_cost(self.cfg, _usage_to_model_result(usage))


def _usage_to_model_result(usage: dict):
    """Build a minimal ModelResult so the shared cost helpers can price a step."""
    return models.ModelResult(
        model_key="", symbol="",
        input_tokens=usage.get("input", 0),
        output_tokens=usage.get("output", 0),
        cache_read_tokens=usage.get("cache_read", 0),
        cache_creation_tokens=usage.get("cache_creation", 0),
    )


def make_loop_client(cfg: config.ModelConfig, task_prompt: str):
    if cfg.provider == "anthropic":
        return AnthropicLoop(cfg, task_prompt)
    if cfg.provider == "openai_compatible":
        return OpenAILoop(cfg, task_prompt)
    if cfg.provider == "ollama":
        return OllamaLoop(cfg, task_prompt)
    raise ValueError(f"unknown provider: {cfg.provider}")


def sdk_available(provider: str) -> tuple[bool, str]:
    """Is the provider's SDK importable? A missing SDK must skip the model, not
    crash the whole run (the shared app venv may not have the notebooks' SDK deps)."""
    try:
        if provider == "anthropic":
            import anthropic  # noqa: F401
        elif provider == "openai_compatible":
            from openai import OpenAI  # noqa: F401
        elif provider == "ollama":
            import ollama  # noqa: F401
        else:
            return False, f"unknown provider {provider!r}"
        return True, ""
    except ImportError as exc:
        return False, str(exc)


# --- Verdict & env ---------------------------------------------------------
def resolve_venv_python() -> str:
    """The shared Poetry venv's python.exe, resolved once via `poetry run python`."""
    out = _run(
        ["poetry", "run", "python", "-c", "import sys; print(sys.executable)"],
        cwd=config.REPO_ROOT, timeout=90,
    )
    py = out.stdout.strip()
    if not py or out.returncode != 0:
        raise RuntimeError(f"could not resolve poetry venv python:\n{out.stderr}")
    return py


def preflight_import(venv_python: str, worktree: Path) -> tuple[bool, str]:
    """Can we `import src.api.main` at the parent commit in the shared venv?"""
    env = {**os.environ, "PYTHONPATH": str(worktree)}
    proc = _run(
        [venv_python, "-c", "import src.api.main"],
        cwd=worktree, env=env, timeout=120,
    )
    if proc.returncode == 0:
        return True, "ok"
    return False, (proc.stderr or proc.stdout)[-2000:]


def install_missing_dep(venv_python: str, message: str) -> bool:
    """If the import failure names a missing module, pip install it into the venv."""
    m = re.search(r"No module named '([^']+)'", message)
    if not m:
        return False
    pkg = m.group(1)
    # Map import name to install name for the one we expect.
    dist = "sentence-transformers" if pkg == "sentence_transformers" else pkg
    print(f"  ! missing dep '{pkg}' -> pip install {dist} into the venv ...", flush=True)
    proc = _run(
        [venv_python, "-m", "pip", "install", dist],
        timeout=600,
    )
    return proc.returncode == 0


def verdict(venv_python: str, worktree: Path) -> dict:
    """Run the scan_stream tests (done-criterion) and the full file (regression)."""
    env = {**os.environ, "PYTHONPATH": str(worktree)}
    out: dict = {}

    def _run_one(label: str, args: list[str]) -> dict:
        argv = [venv_python, "-m", "pytest", *args, "-q", "--no-header",
                "-p", "no:cacheprovider", "--tb=line"]
        proc = _run(argv, cwd=worktree, env=env, timeout=RUN_TESTS_TIMEOUT)
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-1500:]
        return {"passed": proc.returncode == 0, "exit_code": proc.returncode, "tail": tail}

    out["scan_stream"] = _run_one("scan_stream", ["tests/test_api.py", "-k", "scan_stream"])
    if out["scan_stream"]["passed"]:
        out["full"] = _run_one("full", ["tests/test_api.py"])
    return out


# --- Scenario preparation ---------------------------------------------------
def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return _run(["git", *args], cwd=cwd, check=True)


def prepare_worktree(run_dir: Path, model_key: str) -> Path:
    """Fresh worktree at the buggy parent commit, with only the test patch applied."""
    run_dir.mkdir(parents=True, exist_ok=True)
    wt = run_dir / model_key
    if wt.exists():
        _git("worktree", "remove", "--force", str(wt))
    _git("worktree", "prune")
    _git("worktree", "add", "--detach", str(wt), PARENT_COMMIT)
    # Apply ONLY the test patch from the fix commit (defines "done").
    test_src = _git("show", f"{FIX_COMMIT}:{TEST_PATCH_PATH}").stdout
    (wt / TEST_PATCH_PATH).parent.mkdir(parents=True, exist_ok=True)
    (wt / TEST_PATCH_PATH).write_text(test_src, encoding="utf-8")
    return wt


def capture_symptom(venv_python: str, worktree: Path) -> str:
    """Run the scan_stream tests on the buggy tree; record the failing output."""
    env = {**os.environ, "PYTHONPATH": str(worktree)}
    proc = _run(
        [venv_python, "-m", "pytest", "tests/test_api.py", "-k", "scan_stream",
         "-q", "--no-header", "-p", "no:cacheprovider", "--tb=short"],
        cwd=worktree, env=env, timeout=RUN_TESTS_TIMEOUT,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return out[-3500:] if len(out) > 3500 else out


def model_diff_stat(worktree: Path) -> dict:
    """The model's source edits (working tree vs HEAD), src/ only."""
    out = _git("diff", "--numstat", "--", "src/", cwd=worktree).stdout.strip()
    add = del_ = 0
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            a, d, f = parts
            if a != "-" and d != "-":
                add += int(a); del_ += int(d); files.append(f)
    return {"files": files, "insertions": add, "deletions": del_}


def gold_diff_stat() -> dict:
    """The reference fix's size (source files only)."""
    out = _git("show", "--numstat", FIX_COMMIT, "--", *SOURCE_FILES).stdout.strip()
    add = del_ = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] != "-" and parts[1] != "-":
            add += int(parts[0]); del_ += int(parts[1])
    return {"insertions": add, "deletions": del_}


# --- The loop ---------------------------------------------------------------
def run_one_model(
    cfg: config.ModelConfig, task_prompt: str, worktree: Path, venv_python: str,
    *, max_steps: int, run_verdict: bool,
) -> dict:
    harness = ToolHarness(worktree, venv_python)
    client = make_loop_client(cfg, task_prompt)

    steps: list[dict] = []
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    total_cost = 0.0
    total_latency = 0.0
    n_steps = 0
    error: str | None = None
    truncated = False

    print(f"  looping {cfg.label} (budget {max_steps} steps) ...", flush=True)
    for step_idx in range(1, max_steps + 1):
        n_steps = step_idx
        res = client.step()
        if res.error:
            error = res.error
            print(f"    step {step_idx}: ERROR {error}", flush=True)
            break
        # accumulate usage/cost
        for k in totals:
            totals[k] += res.usage.get(k, 0)
        total_cost += client.cost(res.usage)
        total_latency += res.latency
        truncated = truncated or res.truncated
        step_rec = {
            "step": step_idx,
            "tool_calls": [tc["name"] for tc in res.tool_calls],
            "input_tokens": res.usage.get("input", 0),
            "output_tokens": res.usage.get("output", 0),
            "text_preview": (res.text[:200] + "...") if len(res.text) > 200 else res.text,
        }
        steps.append(step_rec)
        names = [tc["name"] for tc in res.tool_calls]
        print(f"    step {step_idx}: {names or '(declares done)'}", flush=True)

        if not res.tool_calls:
            break  # model finished with a plain-text summary
        # execute tools
        results = []
        for tc in res.tool_calls:
            out = harness.dispatch(tc["name"], tc.get("input") or {})
            results.append({"id": tc["id"], "name": tc["name"], "result": out})
        client.feed(results)
    else:
        error = error or f"step budget exhausted ({max_steps})"

    # verdict
    verdict_detail: dict | None = None
    success = False
    if run_verdict:
        verdict_detail = verdict(venv_python, worktree)
        success = bool(verdict_detail.get("scan_stream", {}).get("passed"))
        full_ok = bool(verdict_detail.get("full", {}).get("passed"))
        print(f"    verdict: scan_stream={'PASS' if success else 'FAIL'}"
              f"{'' if not verdict_detail.get('full') else (', full=PASS' if full_ok else ', full=FAIL')}",
              flush=True)
    else:
        print("    verdict: skipped (--no-verdict)", flush=True)

    diff = model_diff_stat(worktree)
    return {
        "label": cfg.label,
        "model_id": cfg.model_id,
        "success": success,
        "n_steps": n_steps,
        "n_tool_calls": dict(harness.calls),
        "n_tool_calls_total": sum(harness.calls.values()),
        "n_edits": harness.n_edits,
        "n_run_tests_calls": harness.calls.get("run_tests", 0),
        "run_tests_history": harness.run_tests_results,
        "total_input_tokens": totals["input"],
        "total_output_tokens": totals["output"],
        "total_cache_read_tokens": totals["cache_read"],
        "total_cost_usd": round(total_cost, 6),
        "total_latency_s": round(total_latency, 3),
        "truncated": truncated,
        "error": error,
        "changed_files": diff["files"],
        "diff_insertions": diff["insertions"],
        "diff_deletions": diff["deletions"],
        "verdict": verdict_detail,
        "steps": steps,
    }


def run(
    model_keys: list[str], *, max_steps: int, run_verdict: bool,
    install_deps: bool, keep_worktree: bool, out_path: Path,
) -> dict:
    print("Resolving Poetry venv ...", flush=True)
    venv_python = resolve_venv_python()
    print(f"  {venv_python}", flush=True)

    run_dir = Path(tempfile.gettempdir()) / f"skingraph_debugloop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # One worktree to pre-flight + capture the symptom (identical for all models).
    print("Preparing scenario worktree (parent commit, test patch applied) ...", flush=True)
    probe_wt = prepare_worktree(run_dir, "_probe")

    pre_ok, pre_msg = preflight_import(venv_python, probe_wt)
    if not pre_ok:
        print("  ! pre-flight import failed:", flush=True)
        print("    " + pre_msg.replace("\n", "\n    ")[:800], flush=True)
        if install_deps:
            if install_missing_dep(venv_python, pre_msg):
                pre_ok, pre_msg = preflight_import(venv_python, probe_wt)
        if not pre_ok:
            print("  ! verdict disabled (run with --install-deps to install missing deps, "
                  "or --no-verdict to run loop-only).", flush=True)
            run_verdict = False

    symptom = capture_symptom(venv_python, probe_wt) if pre_ok else "(pre-flight failed; symptom unavailable)"
    task_prompt = USER_PROMPT.format(symptom=symptom)

    # gold reference size
    gold = gold_diff_stat()
    print(f"  gold fix: +{gold['insertions']}/-{gold['deletions']} lines across {', '.join(SOURCE_FILES)}",
          flush=True)

    # clean the probe worktree (each model gets its own fresh one)
    _git("worktree", "remove", "--force", str(probe_wt))

    results_models: dict[str, dict] = {}
    for key in model_keys:
        cfg = config.MODELS[key]
        if not models.is_available(cfg):
            envs = " or ".join(cfg.api_key_env)
            print(f"  - skipping {cfg.label}: no API key ({envs})", flush=True)
            results_models[key] = {"label": cfg.label, "model_id": cfg.model_id, "skipped": "no_api_key"}
            continue
        sdk_ok, sdk_err = sdk_available(cfg.provider)
        if not sdk_ok:
            print(f"  - skipping {cfg.label}: SDK not installed ({sdk_err})", flush=True)
            results_models[key] = {"label": cfg.label, "model_id": cfg.model_id,
                                   "skipped": "sdk_not_installed", "detail": sdk_err}
            continue
        print(f"\n=== {cfg.label} ({cfg.model_id}) ===", flush=True)
        wt = prepare_worktree(run_dir, key)
        try:
            results_models[key] = run_one_model(
                cfg, task_prompt, wt, venv_python,
                max_steps=max_steps, run_verdict=run_verdict,
            )
        finally:
            if keep_worktree:
                print(f"  kept worktree: {wt}", flush=True)
            else:
                _git("worktree", "remove", "--force", str(wt))

    if not keep_worktree:
        try:
            run_dir.rmdir()
        except OSError:
            pass

    payload = {
        "schema_version": 1,
        "benchmark": "debug_loop",
        "mode": "debug_loop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": {
            "fix_commit": FIX_COMMIT,
            "parent_commit": PARENT_COMMIT,
            "test_patch": TEST_PATCH_PATH,
            "source_files": list(SOURCE_FILES),
            "verdict_target": VERDICT_TARGET,
            "step_budget": max_steps,
            "gold_diff": gold,
        },
        "env": {
            "venv_python": venv_python,
            "preflight_ok": pre_ok,
            "verdict_run": run_verdict,
        },
        "models": results_models,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest = config.RESULTS_DIR / "debug_loop_latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote results -> {out_path}", flush=True)
    print(f"(also -> {latest})", flush=True)
    _print_summary(payload)
    return payload


def _print_summary(payload: dict) -> None:
    print("\n" + "=" * 88)
    print("DEBUG-LOOP SUMMARY")
    print("=" * 88)
    hdr = (f"{'model':<18}{'success':>9}{'steps':>7}{'tools':>7}{'edits':>7}"
           f"{'tests':>7}{'in_tok':>10}{'out_tok':>9}{'cost$':>9}{'diff(+/-)':>12}")
    print(hdr)
    print("-" * 88)
    for key, m in payload["models"].items():
        if "skipped" in m:
            print(f"{m['label']:<18}{'(skipped: ' + m.get('skipped','?') + ')':>62}")
            continue
        d = f"+{m['diff_insertions']}/-{m['diff_deletions']}"
        print(
            f"{m['label']:<18}"
            f"{('PASS' if m['success'] else 'FAIL'):>9}"
            f"{m['n_steps']:>7}"
            f"{m['n_tool_calls_total']:>7}"
            f"{m['n_edits']:>7}"
            f"{m['n_run_tests_calls']:>7}"
            f"{m['total_input_tokens']:>10}"
            f"{m['total_output_tokens']:>9}"
            f"{m['total_cost_usd']:>9.4f}"
            f"{d:>12}"
        )
    gold = payload["scenario"]["gold_diff"]
    print(f"\nGold fix: +{gold['insertions']}/-{gold['deletions']} lines. "
          f"cost = model+provider+caching+tool-token-overhead (history re-sent per step).")


def main(argv: list[str] | None = None) -> int:
    # On Windows the console default codec is cp932; force UTF-8 so a model error
    # or any non-ASCII text never crashes a live run mid-loop.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 — reconfigure isn't always available
            pass
    parser = argparse.ArgumentParser(
        description="Debug-loop benchmark: Opus 4.8 vs GLM-5.2 fix a real backend bug "
        "(commit d11ae62) using tools, scored by pytest.",
    )
    parser.add_argument("--models", default=",".join(config.MODELS),
                        help=f"comma-separated model keys. choices: {', '.join(config.MODELS)}")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"max tool-loop steps per model (default {DEFAULT_STEPS}).")
    parser.add_argument("--no-verdict", action="store_true",
                        help="skip the pytest oracle; report loop mechanics only.")
    parser.add_argument("--install-deps", action="store_true",
                        help="if the pre-flight import fails on a missing dep, pip install it "
                        "into the shared venv (e.g. sentence-transformers).")
    parser.add_argument("--keep-worktree", action="store_true",
                        help="keep the per-model worktrees for inspection (path printed).")
    parser.add_argument("--out", type=Path, default=None,
                        help="output JSON path (default: results/debug_loop_<timestamp>.json).")
    args = parser.parse_args(argv)

    model_keys = [k.strip() for k in args.models.split(",") if k.strip()]
    bad = [k for k in model_keys if k not in config.MODELS]
    if bad:
        parser.error(f"unknown model key(s): {bad}. choices: {list(config.MODELS)}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (config.RESULTS_DIR / f"debug_loop_{stamp}.json")

    run(model_keys, max_steps=args.steps, run_verdict=not args.no_verdict,
        install_deps=args.install_deps, keep_worktree=args.keep_worktree, out_path=out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())