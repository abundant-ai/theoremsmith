import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import {
  Box,
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
import ModelPane from "../components/ModelPane";
import SolvePane from "../components/SolvePane";
import Stages from "../components/Stages";
import StatusChip from "../components/StatusChip";
import { monoFont } from "../theme";
import { useRunStream } from "../useRunStream";

export default function RunView() {
  const { id = "" } = useParams();
  const { run, logs, model, phase, connected } = useRunStream(id);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.config().then(setCfg).catch(() => {});
  }, []);

  // Once the background submit lands the Oddish link, the solver tail takes over.
  useEffect(() => {
    if (run?.result?.oddish) setSubmitting(false);
  }, [run?.result?.oddish]);

  if (!run) return <Text size="2" color="gray">loading</Text>;

  const result = run.result;
  const oddish = result?.oddish;
  const oddishError = result?.oddish_error;
  const canSubmit = run.status === "done" && result?.verified === true;
  const minutes = Math.round((cfg?.oddish_timeout ?? 1800) / 60);
  const showSolve = !!oddish || submitting;
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

  const solveModel = oddish?.model ?? cfg?.oddish_model;
  const solveAgent = oddish?.agent ?? cfg?.oddish_agent;

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

      {oddish && (
        <Callout.Root color="green" variant="surface">
          <Callout.Text>
            Sent to Oddish — {solveAgent} / {solveModel} is solving it now, {minutes}-minute limit.
            Public link:{" "}
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

      {run.error && (
        <Callout.Root color="red" variant="surface">
          <Callout.Text>{run.error}</Callout.Text>
        </Callout.Root>
      )}

      {result?.targets?.length ? (
        <Card size="3">
          <Text size="1" color="gray" as="p" mb="3">
            {result.slots} proof{result.slots === 1 ? "" : "s"} removed
            {result.support ? ` · ${result.support} of them supporting lemmas` : ""}
            {result.verified === true ? " · the grader gives the original proofs reward 1" : ""}
            {result.verified === false ? " · the original proofs did not earn reward 1" : ""}
          </Text>
          <Flex direction="column" gap="3" style={{ maxHeight: 300, overflow: "auto" }}>
            {result.targets.map((t) => (
              <div key={t}>
                <Text size="2" style={{ fontFamily: monoFont, display: "block" }}>
                  {t}
                </Text>
                {result.statements?.[t] && (
                  <div
                    style={{
                      marginTop: 4,
                      maxHeight: 96,
                      overflow: "auto",
                      fontFamily: monoFont,
                      fontSize: 11.5,
                      lineHeight: 1.5,
                      color: "var(--gray-10)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {result.statements[t]}
                  </div>
                )}
              </div>
            ))}
          </Flex>
        </Card>
      ) : null}

      <Flex direction={{ initial: "column", md: "row" }} gap="4">
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Text size="1" color="gray" as="div" mb="2">
            {showSolve
              ? `live solve · ${solveAgent} / ${solveModel}`
              : `builder model · ${cfg?.create_model ?? ""}`}
          </Text>
          {oddish ? (
            <SolvePane runId={id} height={360} />
          ) : submitting ? (
            <Flex
              align="center"
              justify="center"
              gap="2"
              className="mono-panel"
              style={{ height: 360, color: "var(--gray-10)" }}
            >
              <Spinner size="2" />
              <span>loading — setting up the solver on Oddish…</span>
            </Flex>
          ) : (
            <ModelPane model={model} phase={phase} height={360} />
          )}
        </Box>
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Text size="1" color="gray" as="div" mb="2">
            build output {connected ? "" : "(stream closed)"}
          </Text>
          <LogPane
            logs={logs}
            height={360}
            empty={
              run.status === "queued" || run.status === "running"
                ? "waiting for output"
                : "this run has finished; its output is not kept after a restart"
            }
          />
        </Box>
      </Flex>

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
