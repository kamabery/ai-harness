"""ai-harness — a build harness whose state is queryable and whose checks prove themselves.

Two things distinguish it from its predecessor, and both are answers to measured failures:

* **State is typed and queried, never read whole.** `state.json` has one writer (this package)
  and ceilings a check enforces. A phase is handed `harness brief <n>` — a slice — because the
  predecessor's ledger grew to 3,738 lines and whichever section was unbounded absorbed the
  tool output.
* **A check that has not been seen to reject cannot report green.** Every check ships a
  `--selftest` that constructs the input it must refuse. Nine recorded defects in the
  predecessor were checks that could not fail: a green nobody has watched go red and a check
  that cannot go red are the same document.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
