import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import {
  Button,
  Callout,
  Card,
  Code,
  Dialog,
  Flex,
  Heading,
  Link,
  Separator,
  Spinner,
  Text,
  Tooltip,
} from "@radix-ui/themes";

import { api, type Config, type StageState } from "../api";
import LogPane from "../components/LogPane";
import Stages from "../components/Stages";
import StatusChip from "../components/StatusChip";
import { monoFont } from "../theme";
import { useRunStream } from "../useRunStream";

export default function RunView() {
  const { id = "" } = useParams();
  const { run, logs, connected } = useRunStream(id);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.config().then(setCfg).catch(() => {});
  }, []);

  // The background submit lands the Oddish link (or an error) via the poll.
  useEffect(() => {
    if (run?.result?.oddish || run?.result?.oddish_error) setSubmitting(false);
  }, [run?.result?.oddish, run?.result?.oddish_error]);

  if (!run) return <Text size="2" color="gray">loading</Text>;

  const result = run.result;
  const oddish = result?.oddish;
  const oddishError = result?.oddish_error;
  const canSubmit = run.status === "done" && result?.verified === true;
  const minutes = Math.round((cfg?.oddish_timeout ?? 1800) / 60);
  const solveModel = oddish?.model ?? cfg?.oddish_model;
  const solveAgent = oddish?.agent ?? cfg?.oddish_agent;
  const oddishState: StageState = oddish
    ? "done"
    : busy || submitting
      ? "running"
      : submitError || oddishError
        ? "failed"
        : "pending";

  async function submit() {
    setBusy(true);
    setSubmitError("");
    try {
      await api.submit(id);
      setConfirm(false);
      setSubmitting(true);
    } catch (e) {
      setSubmitError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  const targets = result?.targets ?? [];

  return (
    <Flex direction="column" gap="4">
      <Flex align="center" justify="between" gap="3" wrap="wrap">
        <Flex align="baseline" gap="3" wrap="wrap">
          <Text size="1" asChild>
            <RouterLink to="/" style={{ color: "var(--gray-10)", textDecoration: "none" }}>
              runs
            </RouterLink>
          </Text>
          <Heading size="4" weight="medium">
            {run.repo}
          </Heading>
          <Code variant="ghost" color="gray" style={{ fontFamily: monoFont }}>
            {run.sha.slice(0, 10)}
          </Code>
          <StatusChip run={run} />
        </Flex>
        <Flex gap="2">
          {run.status === "done" ? (
            <Button variant="soft" color="gray" asChild>
              <a href={api.taskUrl(run.id)}>Download task</a>
            </Button>
          ) : null}
          {canSubmit && !oddish && !submitting ? (
            cfg && !cfg.oddish_available ? (
              <Tooltip content="the oddish CLI is not available on this server">
                <span>
                  <Button disabled highContrast>
                    Run on Oddish
                  </Button>
                </span>
              </Tooltip>
            ) : (
              <Button onClick={() => setConfirm(true)} highContrast>
                Run on Oddish
              </Button>
            )
          ) : null}
          {oddish ? (
            <Button asChild highContrast>
              <a href={oddish.public_url} target="_blank" rel="noreferrer">
                Open on Oddish ↗
              </a>
            </Button>
          ) : null}
        </Flex>
      </Flex>

      <Stages stages={run.stages} oddish={run.status === "done" ? oddishState : undefined} />

      {run.error && (
        <Callout.Root color="red" variant="surface">
          <Callout.Text>{run.error}</Callout.Text>
        </Callout.Root>
      )}

      {submitting && !oddish && (
        <Callout.Root color="gray" variant="surface">
          <Callout.Text>
            <Flex align="center" gap="2">
              <Spinner size="1" />
              Sending to Oddish — packaging the task and starting {solveAgent} / {solveModel}. The
              public link appears here in a moment.
            </Flex>
          </Callout.Text>
        </Callout.Root>
      )}

      {oddish && (
        <Callout.Root color="green" variant="surface">
          <Callout.Text>
            Sent to Oddish — {solveAgent} / {solveModel} is attempting it now, {minutes}-minute limit.
            Watch it live:{" "}
            <Link
              href={oddish.public_url}
              target="_blank"
              rel="noreferrer"
              style={{ fontFamily: monoFont, wordBreak: "break-all" }}
            >
              {oddish.public_url}
            </Link>
          </Callout.Text>
        </Callout.Root>
      )}

      {!oddish && oddishError && (
        <Callout.Root color="red" variant="surface">
          <Callout.Text>Oddish submit failed: {oddishError}</Callout.Text>
        </Callout.Root>
      )}

      {targets.length ? (
        <Card size="3">
          <Heading size="3" weight="medium" mb="1">
            What the solver has to prove
          </Heading>
          <Text size="2" color="gray" as="p" mb="4">
            A proof is a step-by-step argument that a statement is always true. This task took{" "}
            {result!.slots} proven statement{result!.slots === 1 ? "" : "s"} out of{" "}
            <Code variant="ghost">{run.repo}</Code>, deleted the proof{result!.slots === 1 ? "" : "s"},
            and left a blank in each place. To pass, the solver has to fill every blank with a new
            proof the grader accepts as real.
            {result!.support
              ? ` ${result!.support} of these ${
                  result!.support === 1 ? "is a helper step" : "are helper steps"
                } the main results lean on.`
              : ""}
            {result!.verified === true
              ? " The original proofs pass this grader, so the task is known to be solvable."
              : ""}
          </Text>
          <Flex direction="column" gap="1" style={{ maxHeight: 460, overflow: "auto" }}>
            {targets.map((t, i) => {
              const gloss = result?.glosses?.[t];
              const statement = result?.statements?.[t];
              return (
                <div
                  key={t}
                  style={{
                    padding: "14px 4px",
                    borderTop: i === 0 ? "none" : "1px solid var(--gray-a3)",
                  }}
                >
                  <Flex align="baseline" gap="2">
                    <Text size="1" color="gray" style={{ fontVariantNumeric: "tabular-nums" }}>
                      {i + 1}
                    </Text>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      {gloss ? (
                        <>
                          <Text size="3" as="p" style={{ lineHeight: 1.5 }}>
                            {gloss}
                          </Text>
                          <Text
                            size="1"
                            color="gray"
                            as="p"
                            mt="1"
                            style={{ fontFamily: monoFont }}
                          >
                            {t}
                          </Text>
                        </>
                      ) : (
                        <Text size="3" as="p" style={{ fontFamily: monoFont }}>
                          {t}
                        </Text>
                      )}
                      {statement && (
                        <details style={{ marginTop: 8 }}>
                          <summary
                            style={{
                              cursor: "pointer",
                              listStyle: "none",
                              fontSize: 12,
                              color: "var(--gray-10)",
                              width: "fit-content",
                            }}
                          >
                            the exact statement
                          </summary>
                          <div
                            style={{
                              marginTop: 6,
                              maxHeight: 140,
                              overflow: "auto",
                              fontFamily: monoFont,
                              fontSize: 11.5,
                              lineHeight: 1.5,
                              color: "var(--gray-11)",
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {statement}
                          </div>
                        </details>
                      )}
                    </div>
                  </Flex>
                </div>
              );
            })}
          </Flex>
        </Card>
      ) : null}

      <div>
        <Text size="1" color="gray" as="div" mb="2">
          {run.status === "queued" || run.status === "running"
            ? `building the task${connected ? "" : " (stream closed)"}`
            : "build output"}
        </Text>
        <LogPane
          logs={logs}
          height={targets.length ? 220 : 420}
          empty={
            run.status === "queued" || run.status === "running"
              ? "waiting for output"
              : "this run has finished; its output is not kept after a restart"
          }
        />
      </div>

      <Separator size="4" />
      <Text size="1" color="gray">
        The task directory holds the cut repository under <Code>environment/</Code>, one empty answer
        file per removed proof under <Code>answers/</Code>, the grader under <Code>tests/</Code>, and
        the original proofs under <Code>solution/</Code>.
      </Text>

      <Dialog.Root
        open={confirm}
        onOpenChange={(o) => {
          if (!o && !busy) setConfirm(false);
        }}
      >
        <Dialog.Content maxWidth="480px">
          <Dialog.Title size="4">Run this task on Oddish?</Dialog.Title>
          <Dialog.Description size="2" color="gray">
            Oddish packages this task and runs it with{" "}
            <strong>{cfg?.oddish_agent ?? "claude-code"}</strong> on{" "}
            <strong>{cfg?.oddish_model ?? "fireworks/minimax-m3"}</strong>, with a {minutes}-minute
            limit. It uses your Oddish account and returns a public link where you can watch the
            attempt live.
          </Dialog.Description>
          {submitError && (
            <Text size="1" color="red" as="p" mt="3">
              {submitError}
            </Text>
          )}
          <Flex gap="3" mt="4" justify="end">
            <Button variant="soft" color="gray" onClick={() => setConfirm(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy} highContrast>
              {busy ? "Submitting" : "Run on Oddish"}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </Flex>
  );
}
