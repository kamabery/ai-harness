# Building this harness from scratch

A recipe, not a history. It assumes you have the Shopify article and nothing else, and it ends
with a working harness driving a generated .NET 10 + Aspire project.

Every number in it was measured against three real runs of the predecessor. Where a step exists
because something went wrong, the failure is named in one clause — the reasoning is what makes the
step reproducible, and without it you will cut the wrong thing.

Not auto-loaded. This is a build document.

## What the source actually supplies

Read the article for what it is: **Dispatch**, a Ruby orchestrator running multi-agent *security
scanning* over 80+ existing applications as eight ordered stages — test bootstrap, architecture
documentation, file cataloging, partitioning, hunting, verification, post-processing, reporting.

**It does not describe loop state management.** No checkpoint, no cursor, no retry counter, no
mid-pipeline human gate. Its state is one sentence:

> "All scan data and artifacts are stored in a custom Rails backend and kept up to date by
> subsequent diff-based scans."

That is a **results store queried by content**. A build ledger is a **progress record read whole**.
Different objects, opposite growth curves — and conflating them is the mistake this recipe exists
to route around.

| What transfers | What does not |
|---|---|
| Deterministic scripts over prompts | Partitioning — you cannot partition a file that does not exist yet |
| A hard verification oracle | Parallel fan-out — sequential phase dependency captures none of it |
| Noise is worse than nothing | Commit-diff scanning — there is no previous version of the thing being built |
| A context budget, repointed at what a *phase* is handed | A Rails backend, and 80 apps of amortisation |
| State **shape**: machine-readable, keyed, selectively retrieved, diff-updated | |

## What the measurements say

Do not skip these. Four of them contradict the obvious design.

1. **Cost is tool output, roughly 10:1 over prompt text.** One run's `logs/` was 1.4 MB ≈ 333k
   tokens — 4× that run's entire document payload. Auto-loaded doctrine was 16–25k tokens and was
   implicated in **0 of 9** recorded failures. *Deleting all doctrine recovers under 10% of a run.*
2. **Context volume is anti-correlated with failure.** The run that failed carried the *smallest*
   payload; the most successful carried 2.4× more.
3. **Nine recorded defects were instruments that could not fail**, and not one was an application
   bug: checks whose green was unreachable, evidence excluded by `.gitignore`, markers rendering
   before the thing they stood for.
4. **A positional ceiling relocates growth; a typed one does not.** The predecessor evicted capture
   blocks out of its ledger and the growth moved to the next unbounded section — a cursor that
   reached 420 of 620 lines under a rule that said "exactly one active phase".
5. **Every automated screen assertion is an absence.** Manual testing found defects and poor UX the
   harness could not see, because *nothing detectably wrong* is not *good*.
6. **An audit that ranks mechanisms by recorded catches under-values the ones never switched on.**

## Toolchain

Pinned to what this was built and verified on:

```
uv 0.12.17        Python 3.14.7 (project requires >=3.12)        git 2.31.1.windows.1
PowerShell 7 on PATH (the templates need it)                     .NET 10 SDK
```

## Build order

Not a suggestion — it is the real dependency graph, and each step is testable before the next
exists.

```
state.py            no internal deps      the foundation
  |- memory.py      <- state              cross-run facts and failures
  '- brief.py       <- state              the per-phase slice
check.py            <- state, brief, memory
api.py              <- check, brief, memory, state, detect, importer
cli.py              <- api
                                          alongside, independent:
detect.py <- packs <- assets              tech detection with path:line evidence
guards.py <- ui_guards <- dotnet_guards   architectural rules, one check each
score.py                                  the self-assessment
importer.py                               reads a predecessor's archives
```

## Step 0 — the repository

```powershell
mkdir D:\code\my-harness ; cd D:\code\my-harness
git init
mkdir src\harness, docs, phase-packs, templates, tests\fixtures
```

`pyproject.toml` — the whole of it. **No runtime dependencies on purpose:** a harness that cannot
run because a transitive dependency moved is an instrument that failed silently.

```toml
[project]
name = "my-harness"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
harness = "harness.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["uv_build>=0.9,<0.10"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "harness"
module-root = "src"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`, and the raw directory goes in **now**, before anything can write to it:

```
__pycache__/
.venv/
.pytest_cache/
.harness/raw/
```

```powershell
uv sync
```

## Step 1 — `state.py`

Everything reads it, so nothing precedes it.

**Define the ceilings once**, at module scope, and import them in both the writer and the checker.
The predecessor kept three copies of one pattern in step with a comment saying to keep them
identical; they diverged anyway. *A comment is not a mechanism.*

```python
MAX_STATE_BYTES = 64 * 1024     # more than this is evidence, not state
MAX_STRING      = 1_000         # the anti-paste rule
MAX_NEXT_ACTION = 200           # one action, not a retrospective
MAX_FACTS       = 40            # both real runs settled 36
MAX_FACT_STATEMENT = 300
MAX_CAPTURE_BYTES  = 200 * 1024
```

The model, and the one decision that matters most:

- `Phase{id, name, test, status, needs[], capture_ref, capture_sha, red_seen, needs_human,
  human_saw, counts}`
- `Fact{id, statement, evidence, cost, recheck_cmd, checksum, source, reverified}`
- `Failure{verbatim_first_line, phase, count, resolution, changed_what, changed_in_phase}`
- **`cursor` is one object, not a list.** That makes two active phases *unrepresentable* rather
  than forbidden. The predecessor forbade them in prose and its cursor grew to hold every phase's
  result. Type the constraint or it is a suggestion.

Two rules for the code itself:

- **`validate()` returns a list of defects and never raises.** A check that crashes on bad input is
  a check that cannot report. Do not coerce a malformed cursor in `as_json()` — let it reach
  validation as the defect it is.
- **`save()` refuses rather than writing a defective file.** It calls the same `validate()` the
  check runs, so a file this module wrote cannot fail that check.

Prove it before moving on — the constraint must bite:

```powershell
uv run python -c "from harness import state as S; s=S.State(run='t'); s.cursor=[{'phase':1},{'phase':2}]; print(S.validate(s)[0])"
# -> cursor must be one object, not a list ...      (a defect, not a traceback)

uv run python -c "from harness import state as S; s=S.State(run='t'); s.facts=[S.Fact('A1','x'*5000,'p:1')]; print(len(S.validate(s)))"
# -> 2      (over MAX_STRING, and over MAX_FACT_STATEMENT)
```

## Step 2 — `memory.py`

**One file, not two.** The predecessor split facts and failures across `docs/BUILD-HISTORY/` and
`docs/LESSONS-LEDGER.md`. The second was required to be read first by every run and written at
every archive, and **never existed in either workspace**. Two files let one be dropped silently.

**Carry every row regardless of what the run did with it.** The predecessor's archive said
*"lessons that were APPLIED within the run are … not repeated here"* and kept 3 of 10. The excluded
ones were the render-readiness family, and the next run in the same repository re-derived four of
them three days later. *A lesson applied inside one run does not mean the next run knows it.*

**The inherit gate** — the only Shopify mechanism that transfers:

| cost | meaning | gate |
|---|---|---|
| `cheap` | re-checkable in about a second, no build | **always re-run**, never inherit |
| `expensive` | needs a build, a browser, or enumerates more than a handful | **inherit while the checksum matches** |

An inherited fact arrives `source="inherited"` and **stays open until this run has watched its
re-check pass**. Otherwise a citation becomes a signal — which is how the predecessor ended up with
36 facts of which 5 cited the archive that already held them.

## Step 3 — `brief.py`

The one idea worth taking from the article, repointed. Their partitioning sizes each agent's input
to 20–30% of the window; you have no files to partition, but you have the same problem one level
up — **what is a phase handed?**

`harness brief <n>` emits, and nothing else:

1. phase `n`, and phase `n-1` for the baseline it is compared against
2. the cursor — one line
3. **only the facts phase `n` names in `needs[]`**
4. failures still open, and any that hit the two-identical stop
5. the baseline counts

Phase 0 additionally gets memory, because that is where re-deriving a known fact is cheapest to
avoid. **Target 2 KB, hard ceiling 4 KB**, and a check enforces it. Measured on a run with 36
facts: **1,072 bytes, naming 3.**

> **Prerequisite the predecessor lacked.** Facts need ids (`A1`, `A2`, …) and every phase an
> explicit `needs: [A3, A7]`. Its plan referenced facts only in prose and its assumption rows had
> no identifiers at all, so no slice was computable from it. Add both before writing this module.

## Step 4 — `check.py`

**The rule above the rules:**

> A check that has never been seen to reject cannot report green.

Every check ships a `selftest()` that constructs the input it must refuse and asserts refusal.
`run_all` marks any check whose selftest did not run as `UNPROVEN` and counts it a defect.

This is **not** a substitute for unit tests, and the distinction is the whole point. The
predecessor had **2,041 lines of tests across four fixture workspaces** and all nine instrument
defects shipped anyway, because a unit test proves a function rejects a *fixture* — not that the
check, as wired into this workspace, rejects *this workspace's* failing case.

Ten checks:

| Check | Decides |
|---|---|
| `state` | the schema and every ceiling; a passed phase's capture hashes to what state recorded |
| `brief` | every slice is still a slice, and names the facts it needs |
| `baseline` | executed **and skipped** counts, number for number, never relaxed to `>=` |
| `red` | no phase closed on a green nobody watched go red, and the pair is two different runs |
| `evidence-visible` | every cited path survives a clone; committed evidence has not silently moved |
| `ignore` | the raw stream is gitignored, and nothing cites it |
| `memory` | what a previous run paid for was read, and this run's was written |
| `spec-coverage` | every deliverable the spec asserts maps to a command that runs |
| `approved` | a person looked at what a person will see |
| `selftest` | every check above has been seen to reject its own bad input |

Three corollaries, each from a recorded failure:

- **Every counting check asserts a floor**, never only a ceiling. *Zero is trivially true of
  nothing* — a page that rendered nothing scored `overflow=False consoleErrors=0 axe=0`.
- **No check may match text it or its own template authored.** A gate using
  `Contains("IN_PROGRESS")` matched the legend line that *defines* the word, so it was true in
  every run that has ever existed.
- **Presence, not just existence.** The predecessor's capture check asserted the file existed; ten
  files existed as 818-byte templates reading `(nothing captured yet)`. Hash the content.

```powershell
uv run harness selftest        # 0 defects over N examined, before any green is worth anything
```

### The check most people cut, and why not to

`approved` has zero recorded catches. Cut it on that basis and you repeat the mistake this recipe
was written after: **its return was zero because it was never switched on**, not because it failed.

It exists because every automated screen assertion is an *absence*. A real run's visual criterion
was literally six of them, printed per screen:

```
overflow=False  colour==bg=0  svgNoPaint=0  unnamedControls=0  consoleErrors=0  axe(ser/crit)=0
```

All six go green on a screen that is cramped, badly ordered, or missing what the user came for.
So a phase that changes something a person sees is marked `needs_human`, and closing it without

```
APPROVED-BY: <name> <date>
SAW: <which screens, which viewports, which themes>
```

is a state defect. An agent could type both lines — worth saying plainly rather than implying a
guarantee this cannot give. What the format buys is that forging it is a *lie*, attributed and
dated about named screens, rather than the silent omission an unwritten judgement is.

## Step 5 — `api.py` and `cli.py`

Three rules, inherited from the predecessor because they were right there:

- **A refusal is a result**, not an exception. `code 1`, reason as the first line. Callers read a
  return value.
- **Nothing defaults to the current directory.** The workspace is always an argument. A shell's cwd
  is not evidence of which tree a request meant, and scaffolding into the wrong one is invisible
  from inside the documents — they read as authoritative against a repository nobody meant.
- **Nothing half-completes.**

The exit code is the defect count. And one line that is not optional:

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

A Windows console is cp1252, and a report quoting a tree's own text will eventually carry an arrow
or an em-dash. Without this the command dies *after* doing its work — a report that fails on its
own output, which is the same shape as a check that cannot fail.

## Step 6 — doctrine, under an enforced ceiling

**Auto-loaded: `CLAUDE.md` ≤ 120 lines + `docs/ARCHITECTURE.md` ≤ 150.** Everything else is read on
demand: `STANDARDS.md` and `CONTROLS.md` ≤ 250 each, four phase packs ≤ 60 each.

Achieved here: **542 lines** across `STANDARDS.md`, `CONTROLS.md`, the four phase packs and the
three templates, of which **~1,321 tokens auto-load** — against the predecessor's 4,702 and
~26,000 for the same set. (This build document is not counted; it is not doctrine and never
loads into a run.)

**Trim for legibility, not cost.** Doctrine is under 10% of a run's spend and appeared in 0 of 9
failures. Cut it because unenforced prose is a suggestion that reads as a guarantee — the
predecessor's own phase pack says *"a rule with no check and no reviewer note is decoration, and
every later run inherits it as though somebody enforced it"*, and then its cursor rule was exactly
that.

One thing the SPEC template must carry, and it is not optional:

> **`## What it must feel like to use`**

The rule "a criterion that describes a feeling never prints, so no phase can close on it" is
correct about testability and **wrong about disposal**. UX quality lives entirely in that category,
so the rule was deleting requirements rather than routing them. All eight of one run's success
criteria were counts, status codes, a string transform, an exit code, or the six absences — none
said whether the product was good to use, and manual testing later found what that missed.

Unobservable requirements go in that section, and from there to the `approved` sign-off. *An
unobservable requirement that is written down is a question for a person; one that was filtered out
is a defect nobody is looking for.*

## Step 7 — the run shape, and the generator seam

**Four fixed phases plus slices**, down from 10–13 of which 7 produced no product code:

| Phase | For |
|---|---|
| `0 preflight` | facts resolved; every gate run against the case it must reject |
| `1 baseline` | instruments up, red channel proved, executed and skipped counts recorded |
| `2..N slice-k` | **the only phases producing product code** |
| `N+1 reconcile` | cleanup and archive, merged |

Cut: the README phase, the self-improvement phase, the separate archive, and the standalone
adversarial review. That last one on its own record — two blind reviewers ruled
`9 PROVEN / 0 NOT PROVEN` over a tree where a named `SPEC.md` deliverable had never been built, and
a `git status --porcelain` read against the spec found it a day later. Its **withheld-evidence
control** was 2-for-2 and survives as one subagent call inside `reconcile`.

### The generator goes in front, and stays a separate repository

`D:\code\template-projects` emits the starting code: a .NET 10 + Aspire solution with ~76 tests, a
committed `contracts/api.openapi.json` whose `ContractTests` fails on drift, `/harness/*`
fault-injection endpoints, an OKLCH design system with documented WCAG AA measurements, and Azure
Terraform.

**Do not merge it into the harness.** Different lifecycles — it ships as a versioned NuGet artifact
consumed by `dotnet new`; the harness is a per-workspace Python tool. Different scope — it is
.NET/Aspire specific and carries a live reference implementation, the harness is stack-agnostic
across seven detection packs. And the article's own division: *hand agents deterministic scripts*.
A generator **is** the deterministic component; it needs to be callable, not resident.

```powershell
# --- generator stage ---
cd D:\code\template-projects
pwsh templating/stage.ps1
dotnet pack packaging/AspireStarter.Templates.csproj -c Release -o artifacts/nupkg
dotnet new uninstall AspireStarter.Templates      # do NOT use --force
dotnet new install artifacts/nupkg/AspireStarter.Templates.1.0.0.nupkg

dotnet new aspire-base     -n MyProject -o D:\code\MyProject --dbProvider postgres --resource Product
dotnet new aspire-ui-react -n MyProject -o D:\code\MyProject --resource Product
# apply .scaffold/*.wiring.md into MyProject.slnx and .aspire/apphost.cs, then delete .scaffold/
cd D:\code\MyProject ; git init ; git add -A ; git commit -m "Scaffolded"
dotnet build ; dotnet test

# --- harness stage ---
cd D:\code\my-harness
uv run harness -C D:\code\MyProject import D:\code\Scratchpad\whats-next   # optional, if a predecessor exists
uv run harness -C D:\code\MyProject start first-slice --slices 3 --project MyProject
uv run harness -C D:\code\MyProject inherit
uv run harness -C D:\code\MyProject brief 0
uv run harness -C D:\code\MyProject check
uv run harness -C D:\code\MyProject score
```

**Phase 1 becomes confirmation, not construction.** The generator already emitted the instruments,
so record them as facts carrying their re-check commands rather than building them again:

| Fact | `recheck_cmd` | cost |
|---|---|---|
| the test command and its executed count | `dotnet test MyProject.slnx` | cheap |
| the red channel exists and can be fired | `POST /harness/fail-next` | cheap |
| the committed contract matches the running API | `dotnet test tests/myproject.api.tests --filter ContractTests` | cheap |
| the design tokens and their WCAG measurements | the style-token check | expensive |

**One thing the generator does not give you:** React ships no `test` script at all, so a
React-only scaffold has no front-end suite. The harness's zero-tests-executed rule will fail the
phase, correctly — that is the gap surfacing, not the harness misbehaving.

### The detection fix this seam required

A generated solution is `MyProject.slnx`, and `**/*.sln` does not match it — so every scaffolded
solution file was invisible. Its MAUI head declares `<TargetFrameworks>` (plural), which the
single-form capture missed entirely, so a `net9.0-android` would have passed unseen.

Both are fixed in `tech-packs/dotnet/pack.json`, and the second needed a new idea rather than a
wider regex: `expect_each`, a pattern every item of a multi-valued capture must match.
`net10.0-android;net10.0-ios` is .NET 10 and equals no single expected string, so exact comparison
would report a conflict that is not one — and **noise sent to a developer is worse than no finding
at all.** The pack declares how to compare; the detector stays stack-agnostic.

## Verification

```powershell
uv run pytest tests/ -q          # 106 tests
uv run harness selftest          # PASS - 0 defect(s), examined 9
```

Against the only ground truth there is — the predecessor's real runs:

1. **Import** the old workspaces and assert memory carries the render-readiness family the old
   archive excluded by rule (`post-change invariant`, `assignedSlot`).
2. **The memory gate** must fail the abandoned run at phase 0 for inheriting nothing.
3. **The ceilings** must reject that era's 195 KB capture section (the 1,000-char string rule) and
   its 420-line cursor (the cursor-is-an-object type).
4. **Detection** must name `MyProject.slnx` with a `path:line` and record a MAUI multi-target
   without raising a conflict, while still flagging `net9.0-android`.
5. **A screen-touching phase** must refuse to close without `APPROVED-BY` and `SAW:`.

## What this does not fix

The ~200k tokens per phase of browser and build output, which is the dominant cost. Every ceiling
here recovers under 10% of a phase, and the run that failed carried the smallest payload. What this
buys is **falsifiability**, not cheapness.

The remaining lever is fewer assertions per slice — and that trade surrenders the instruments that
caught most of the recorded bugs. It is a decision to take deliberately, with measured token spend
in hand, which does not exist until you have run this once.
