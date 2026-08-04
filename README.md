# theoremsmith

Point it at a Lean 4 repository. It builds the repository, reads the real dependency graph out of
the compiled environment, picks a theorem, deletes that theorem's proof along with every helper
lemma that existed only to support it, and writes out a self-contained task: a repository that no
longer compiles, a slot for each missing proof, and a grader that decides whether a submitted proof
is real.

You watch the whole thing happen in the browser while it runs.

## Run it

```bash
cp .env.example .env   # put your key in it
docker compose up --build
```

Open <http://localhost:8000>, press **New run**, paste a repository like
`avigad/mathematics_in_lean`, and watch.

Any OpenAI-compatible endpoint works. The default is Kimi:

| Variable | Default |
| --- | --- |
| `THEOREMSMITH_API_KEY` | — (required) |
| `THEOREMSMITH_BASE_URL` | `https://api.moonshot.ai/v1` |
| `THEOREMSMITH_MODEL` | `kimi-k2-0905-preview` |
| `THEOREMSMITH_MAX_RUNS` | `2` |
| `THEOREMSMITH_DATA` | `/data` |

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

Grading is binary. A submission is applied by splicing each answer file in after the theorem's
`:=` — the statement itself comes from `tests/slots.json`, not from the submission, so the theorem
cannot be weakened. Then the environment is rebuilt and every target's axiom closure is collected;
anything beyond `propext`, `Classical.choice`, and `Quot.sound` fails. `sorry`, `admit`, `axiom`,
`native_decide`, and the kernel-trust options are rejected before the build runs.

Every run ends by splicing `solution/` back in and rebuilding. If the original proofs do not
reconstitute the repository, the run is marked failed rather than shipped.

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

## License

MIT.
