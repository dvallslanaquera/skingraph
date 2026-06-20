"""Deterministic ground truth for the Blast Radius questions.

The oracle answers "where does symbol X occur?" with pure static analysis, so it is
independent of any LLM. For a rename, the set of lines that must change is exactly the
set of lines containing the identifier as a *whole token* (definition + every
reference). That is what ``rg -nw <symbol>`` computes; we reimplement it in pure
Python so the benchmark has no external binary dependency and runs identically on
Windows, macOS, and Linux.

Identifier-boundary matching (not plain substring) avoids two failure modes:
matching ``UserProfile`` inside ``UserProfileError``, and matching it inside a longer
word. Distinctive symbol names (see ``config.TARGET_SYMBOLS``) keep false positives
from comments/strings negligible; any that remain are part of the documented oracle
definition rather than a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .repo_context import list_source_files

# An identifier char on either side disqualifies the match (so `foo_X` / `Xbar` are
# not hits, but `state.X`, `X,`, `(X)` are).
_BOUNDARY = r"(?<![A-Za-z0-9_]){sym}(?![A-Za-z0-9_])"


@dataclass(frozen=True)
class Reference:
    file: str
    line: int
    text: str  # the source line, stripped, for human inspection


@dataclass(frozen=True)
class SymbolOracle:
    symbol: str
    references: tuple[Reference, ...]

    @property
    def files(self) -> set[str]:
        return {r.file for r in self.references}

    @property
    def line_keys(self) -> set[tuple[str, int]]:
        return {(r.file, r.line) for r in self.references}


@dataclass(frozen=True)
class Oracle:
    by_symbol: dict[str, SymbolOracle] = field(default_factory=dict)

    def __getitem__(self, symbol: str) -> SymbolOracle:
        return self.by_symbol[symbol]


def find_references(symbol: str, repo_root: Path | None = None) -> SymbolOracle:
    """Every whole-token occurrence of ``symbol`` across tracked source files."""
    repo_root = repo_root or config.REPO_ROOT
    pattern = re.compile(_BOUNDARY.format(sym=re.escape(symbol)))
    refs: list[Reference] = []
    for rel in list_source_files(repo_root):
        text = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                refs.append(Reference(file=rel, line=i, text=line.strip()))
    return SymbolOracle(symbol=symbol, references=tuple(refs))


def build_oracle(
    symbols: tuple[str, ...] | None = None, repo_root: Path | None = None
) -> Oracle:
    symbols = symbols or config.TARGET_SYMBOLS
    return Oracle(by_symbol={s: find_references(s, repo_root) for s in symbols})


if __name__ == "__main__":  # python -m blast_radius.oracle
    oracle = build_oracle()
    print(f"{'symbol':<32} {'files':>6} {'lines':>6}")
    print("-" * 46)
    for sym, so in oracle.by_symbol.items():
        print(f"{sym:<32} {len(so.files):>6} {len(so.references):>6}")
