"""Build the single-string repository dump fed to the models.

The dump is deterministic: files come from ``git ls-files`` (tracked files only),
filtered to source extensions, sorted, each under a clear header, with every line
prefixed by its 1-based line number. Injecting the line numbers is deliberate — it
lets us score the models at line granularity *fairly*: the model reads line numbers
off the margin instead of having to count newlines in an 80k-token blob, so a miss
reflects retrieval ability, not arithmetic.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class RepoContext:
    text: str                  # the full dump handed to the model
    files: tuple[str, ...]     # repo-relative POSIX paths, in dump order
    char_count: int
    est_tokens: int


def list_source_files(repo_root: Path | None = None) -> list[str]:
    """Tracked source files (POSIX-relative), sorted, restricted to SOURCE_GLOBS."""
    repo_root = repo_root or config.REPO_ROOT
    out = subprocess.run(
        ["git", "ls-files", *config.SOURCE_GLOBS],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    files = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return sorted(files)


def _read_lines(path: Path) -> list[str]:
    # newline="" off; we only need the textual content. Tolerate stray bytes.
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def build_context(repo_root: Path | None = None) -> RepoContext:
    """Concatenate every source file into one line-numbered, header-delimited string."""
    repo_root = repo_root or config.REPO_ROOT
    files = list_source_files(repo_root)

    chunks: list[str] = []
    for rel in files:
        lines = _read_lines(repo_root / rel)
        header = f"===== FILE: {rel} ({len(lines)} lines) ====="
        body = "\n".join(f"{i:>5} | {line}" for i, line in enumerate(lines, start=1))
        chunks.append(f"{header}\n{body}")

    text = "\n\n".join(chunks)
    char_count = len(text)
    est_tokens = round(char_count / config.CHARS_PER_TOKEN_ESTIMATE)
    return RepoContext(
        text=text,
        files=tuple(files),
        char_count=char_count,
        est_tokens=est_tokens,
    )


if __name__ == "__main__":  # quick manual inspection: python -m blast_radius.repo_context
    ctx = build_context()
    print(f"{len(ctx.files)} source files")
    print(f"{ctx.char_count:,} chars  (~{ctx.est_tokens:,} tokens estimated)")
    print("first files:", ", ".join(ctx.files[:5]))
