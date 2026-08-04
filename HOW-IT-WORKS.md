# How it works

Theoremsmith turns a Lean 4 repository into a benchmark task and writes the result as a directory:
the repository with some proofs removed, one answer file per removed proof holding the placeholder
`sorry`, a grader, the proofs that were removed, and a short instruction. Nobody writes the task by
hand. The theorems are ones people already proved, the difficulty is whatever those proofs actually
required, and the mark is 0 or 1, decided by the Lean compiler rather than by an opinion. An answer
file holds one Lean expression, which is spliced in on the right of `:=` — either a proof term, a
Lean expression whose type is the theorem being claimed, or a tactic block beginning with `by`.
Solving the task means proving those same statements again inside the copy, without the proofs that
are gone.

Which proofs to remove is decided from the compiled repository rather than from reading the source.
A run clones the repository, builds it with Lake, Lean's build tool, and then runs a small Lean
program against that build. For every declaration the repository itself defines, that program
reports three things: the names appearing in the declaration's type, which is the statement being
claimed; the names appearing in its value, which for a theorem is the proof; and the file and line
range it was written on. Those reports form a directed graph over the repository's own
declarations, with one kind of edge for statements and another for proofs. A dependency on anything
outside the repository, mathlib included, is not in that graph, so the cut cannot see it and never
touches it. A few goal theorems are chosen, either named by whoever started the run or picked by a
language model from a shortlist of theorems whose proofs lean on several others in the same
repository. Everything reachable from a goal along either kind of edge is the working set. Whatever
the goals' statements need stays, because otherwise those statements would no longer typecheck, and
so does anything the rest of the repository still refers to. What is left over is exactly the
theorems that existed only to prove the goals. Those, and the goals themselves, lose their proofs:
the statement stays in the file and keeps its `:=`, the proof becomes a single marker line, and the
removed text is saved as the answer. That is where the difficulty comes from. The helper lemmas are
still stated, but nothing proves them any more, so a solver has to rebuild the argument instead of
citing it.

Grading has to survive a solver who would rather edit the problem than solve it, so it does not
trust the repository it is handed. Each answer is spliced back in at its marker, but only after the
lines above that marker are compared against the statement the task recorded when it made the cut.
If they differ at all, the submission is refused rather than graded, so proving something weaker is
not available. The answer text is then scanned, with comments, string literals and character
literals removed first so nothing can hide inside them. It is refused if its brackets do not
balance, or if it contains `sorry`, `axiom`, `native_decide`, or any of the options that tell Lean
to skip its kernel, the small trusted program that rechecks every proof. Only then is the
repository rebuilt. Last, the grader asks Lean which axioms each finished proof depends on. An
axiom is a name the kernel accepts with a type and no proof, so a solver who declares one anywhere
in the tree and quietly uses it would otherwise pass. Three are allowed, the ones ordinary Lean
mathematics already rests on: `propext`, propositional extensionality; `Classical.choice`; and
`Quot.sound`, quotient soundness. Anything else, or a target the audit cannot find at all, scores
zero. That whole grader is then run once more against the proofs that were removed in the first
place. The run is reported as finished only if they earn full marks: a task its own answers cannot
pass is a broken task, and it is never shipped.
