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

Open <http://localhost:8000>, press **New run**, paste `leanprover-community/batteries`, and watch.

A repository that depends on mathlib works too, but the first run fetches mathlib's build cache and
takes much longer; raise `THEOREMSMITH_BUILD_TIMEOUT` before trying one.

Any OpenAI-compatible endpoint works. The default is Kimi:

| Variable | Default |
| --- | --- |
| `THEOREMSMITH_API_KEY` | — (required) |
| `THEOREMSMITH_BASE_URL` | `https://api.moonshot.ai/v1` |
| `THEOREMSMITH_MODEL` | `kimi-k2-0905-preview` |
| `THEOREMSMITH_MAX_RUNS` | `2` |
| `THEOREMSMITH_DATA` | `/data` |
| `THEOREMSMITH_BUILD_TIMEOUT` | `3600` seconds |
| `THEOREMSMITH_PROBE_TIMEOUT` | `900` seconds |
| `THEOREMSMITH_CLONE_TIMEOUT` | `600` seconds |

For OpenRouter, set `THEOREMSMITH_BASE_URL=https://openrouter.ai/api/v1` and
`THEOREMSMITH_MODEL=moonshotai/kimi-k2`.

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
  emit.py       writes the task directory and the grader
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
