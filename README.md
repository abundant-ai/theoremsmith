# theoremsmith

Point it at a Lean 4 repository. It builds the repository, reads the real dependency graph out of
the compiled environment, picks a theorem, and removes that theorem's proof along with the proof of
every helper lemma that existed only to support it. What comes out is a self-contained task: a
repository whose proofs are now `sorry`, one empty answer file per missing proof, and a grader that
decides whether a submitted proof is real.

You watch the whole thing happen in the browser while it runs, model output included.

A run against `leanprover-community/batteries` takes about two minutes on a warm box and produces a
task around three theorems and the lemma they shared.

## Run it

```bash
cp .env.example .env   # put your key in it
docker compose up --build
```

Open <http://localhost:8000>, press **New run**, paste `leanprover-community/batteries`, and press
**Scan theorems**. That clones the source (no build) and offers ten theorems, each with a one-line
plain-language description; tick the ones you want and press **Build task**.

A repository that depends on mathlib works too, but the first run fetches mathlib's build cache and
takes much longer; raise `THEOREMSMITH_BUILD_TIMEOUT` before trying one.

The **create** model runs the scan, the theorem choice, and the description, through one
OpenAI-compatible endpoint (OpenRouter by default).

## Send it to Oddish

theoremsmith builds the task; it does not solve it. When a run finishes and its original proofs
earn reward 1, the run page offers **Run on Oddish**. It asks first, then packages the task as a
Harbor task (a `Dockerfile` that pins the repo's Lean toolchain and pre-builds it, a `task.toml`,
and a verifier that runs the shipped grader) and hands it to the [Oddish](https://oddish.app) CLI:

```
oddish run <task> -a claude-code -m fireworks/minimax-m3 --publish --background --json
```

Oddish runs it under Claude Code on MiniMax M3 (via Fireworks) under a 30-minute limit, and returns a
public link where you watch the attempt live. This needs the `oddish` CLI installed and signed in on the server;
the button is disabled otherwise. Change the solver with `THEOREMSMITH_ODDISH_MODEL` (any id
`oddish run -m` accepts).

| Variable | Default |
| --- | --- |
| `THEOREMSMITH_API_KEY` | — (required; `OPENROUTER_API_KEY` is also read) |
| `THEOREMSMITH_BASE_URL` | `https://openrouter.ai/api/v1` |
| `THEOREMSMITH_CREATE_MODEL` | `moonshotai/kimi-k2.7-code` |
| `THEOREMSMITH_ODDISH_AGENT` | `claude-code` |
| `THEOREMSMITH_ODDISH_MODEL` | `fireworks/minimax-m3` |
| `THEOREMSMITH_ODDISH_TIMEOUT` | `1800` seconds (the agent's limit on Oddish) |
| `THEOREMSMITH_ODDISH_ENV` | — (Oddish picks; e.g. `daytona`) |
| `THEOREMSMITH_MAX_RUNS` | `2` |
| `THEOREMSMITH_DATA` | `/data` |
| `THEOREMSMITH_EXAMPLES` | the three verified example repos (override: `owner/a\|note, owner/b`) |
| `THEOREMSMITH_BUILD_TIMEOUT` | `3600` seconds |
| `THEOREMSMITH_PROBE_TIMEOUT` | `900` seconds |
| `THEOREMSMITH_CLONE_TIMEOUT` | `600` seconds |

## Host it on Daytona

The repository carries a `.devcontainer/`, so Daytona builds and starts it directly:

```bash
daytona create https://github.com/<you>/theoremsmith
```

Set `THEOREMSMITH_API_KEY` in your Daytona environment before creating the sandbox; the
devcontainer forwards it in and exposes port 8000. A sandbox needs a few GB of disk for Lean
toolchains and build artifacts, and `THEOREMSMITH_MAX_RUNS=1` is the right setting on a small one —
`lake build` is the expensive part of a run, not the model.

## Run it without Docker

You need `git`, Python 3.11+, Node 20+, and [elan](https://github.com/leanprover/elan).

```bash
pip install -e ".[dev]"
(cd web && npm install && npm run build)
theoremsmith
```

## What a run produces

```
task/
  instruction.md      what the solver is told
  environment/        the repository with the proofs cut out
  answers/            one file per missing proof, each containing `sorry`
  tests/              apply_answers.py, grade.py, axioms.lean, run_test.sh
  solution/           the original proofs
  task.json
```

Grading is binary. Each blanked proof leaves its statement in place followed by a marker line, and
a submission is applied by replacing only that marker. Before it is applied, the lines above the
marker are compared against the statement stored in `tests/slots.json`, so a submission that
weakened the theorem is rejected rather than graded. `sorry`, `admit`, `axiom`, `native_decide` and
the kernel-trust options are rejected at the same point, after comments, strings and character
literals are stripped from the answer. The environment is then rebuilt, and `#print axioms` is run
over every target; anything beyond `propext`, `Classical.choice` and `Quot.sound` fails, which is
what catches an axiom the solver declared in a file of their own.

Every run ends by running that same grader over `solution/`. If the original proofs do not earn
reward 1 from the shipped grader, the run is marked failed rather than shipped.

The grader lives inside the task directory, so a solver that can write to `tests/` can rewrite it.
Restore `tests/` from the task archive before grading, or mount it read-only. `task.json` carries
the sha256 of every file under `tests/` so tampering is detectable.

## Layout

```
server/theoremsmith/
  app.py        HTTP API and SSE stream
  pipeline.py   the seven stages of a run
  lean.py       git, lake, and the probe
  dagcut.py     the dependency graph and the cut
  scan.py       the pre-build theorem scan behind the menu
  emit.py       writes the task directory and the grader
  harbor.py     repackages a finished task for Oddish/Harbor
  oddish.py     submits a task through the Oddish CLI
  llm.py        streaming OpenAI-compatible client
  store.py      runs on disk
  events.py     the event bus behind the live view
  assets/dag_probe.lean
web/            React + MUI front end
```

## Tests

```bash
pytest
```

The Lean end-to-end tests build a tiny package, cut it, and run the shipped grader for real: the
original proofs earn reward 1, a `sorry` is refused before the build, an axiom the solver declares
in a file of their own earns reward 0, and a weakened statement is refused. They skip themselves
when `lake` is not on `PATH`.

## License

MIT.
