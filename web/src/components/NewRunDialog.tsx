import { useEffect, useRef, useState } from "react";
import { Box, Button, Checkbox, Dialog, Flex, Spinner, Text, TextField } from "@radix-ui/themes";

import { api, type Example, type Run, type ScanOption } from "../api";
import { monoFont } from "../theme";

type Phase = "form" | "scanning" | "pick";

export default function NewRunDialog({
  open,
  onClose,
  onCreated,
  examples = [],
  initialRepo = "",
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (run: Run) => void;
  examples?: Example[];
  initialRepo?: string;
}) {
  const [repo, setRepo] = useState(initialRepo);
  const [sha, setSha] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [options, setOptions] = useState<ScanOption[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [scanLog, setScanLog] = useState("");
  const stream = useRef<EventSource | null>(null);
  const logBox = useRef<HTMLDivElement>(null);

  const stopStream = () => {
    stream.current?.close();
    stream.current = null;
  };

  useEffect(() => {
    const el = logBox.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scanLog]);

  useEffect(() => {
    if (open) {
      setRepo(initialRepo);
      setPhase("form");
    }
  }, [open, initialRepo]);

  useEffect(() => stopStream, []);

  function reset() {
    stopStream();
    setRepo("");
    setSha("");
    setPhase("form");
    setOptions([]);
    setPicked(new Set());
    setError("");
    setScanLog("");
  }

  function close() {
    onClose();
    reset();
  }

  function scan() {
    setPhase("scanning");
    setError("");
    setScanLog("");
    stopStream();
    const source = new EventSource(api.scanStreamUrl(repo, sha));
    stream.current = source;
    source.onmessage = (e) => {
      const d = JSON.parse(e.data) as { text?: string; options?: ScanOption[]; error?: string };
      if (d.error) {
        stopStream();
        setError(d.error);
        setPhase("form");
        return;
      }
      if (d.text != null) {
        setScanLog((prev) => (prev + d.text).slice(-4000));
        return;
      }
      if (d.options != null) {
        stopStream();
        if (!d.options.length) {
          setError("nothing in this repository was worth cutting into a task");
          setPhase("form");
          return;
        }
        setOptions(d.options);
        setPicked(new Set());
        setPhase("pick");
      }
    };
    source.onerror = () => {
      stopStream();
      setPhase((p) => {
        if (p === "scanning") {
          setError("the scan connection dropped");
          return "form";
        }
        return p;
      });
    };
  }

  function toggle(name: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  async function create(goals: string[]) {
    setBusy(true);
    setError("");
    try {
      const glosses = Object.fromEntries(
        options.filter((o) => picked.has(o.name)).map((o) => [o.name, o.gloss]),
      );
      const run = await api.create(repo, sha, goals, glosses);
      onCreated(run);
      close();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && close()}>
      <Dialog.Content maxWidth="540px">
        <Dialog.Title size="4">New run</Dialog.Title>

        {phase !== "pick" && (
          <Flex direction="column" gap="3">
            <label>
              <Text size="1" color="gray" as="div" mb="1">
                Lean 4 repository
              </Text>
              <TextField.Root
                placeholder="owner/name"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                disabled={phase === "scanning"}
                autoFocus
              />
            </label>
            {examples.length > 0 && (
              <Flex gap="2" wrap="wrap">
                {examples.map((ex) => (
                  <Button
                    key={ex.repo}
                    variant="soft"
                    color="gray"
                    size="1"
                    onClick={() => setRepo(ex.repo)}
                    disabled={phase === "scanning"}
                    title={ex.note ? `${ex.repo} — ${ex.note}` : ex.repo}
                    style={{ fontFamily: monoFont }}
                  >
                    {ex.repo.split("/")[1]}
                  </Button>
                ))}
              </Flex>
            )}
            <label>
              <Text size="1" color="gray" as="div" mb="1">
                Commit (optional)
              </Text>
              <TextField.Root
                placeholder="defaults to the default branch"
                value={sha}
                onChange={(e) => setSha(e.target.value)}
                disabled={phase === "scanning"}
              />
            </label>
            <Text size="1" color="gray">
              Scanning clones the repository and reads every theorem in it. For a repository that
              hasn't been scanned before this can take many minutes. The examples above are
              pre-scanned and open instantly.
            </Text>
            {phase === "scanning" && (
              <Flex direction="column" gap="2">
                <Flex align="center" gap="2">
                  <Spinner size="1" />
                  <Text size="1" color="gray">
                    reading {repo} and choosing theorems — this can take many minutes…
                  </Text>
                </Flex>
                {scanLog && (
                  <div
                    ref={logBox}
                    className="mono-panel mono-panel--muted"
                    style={{ maxHeight: 150, fontSize: 11 }}
                  >
                    {scanLog}
                  </div>
                )}
              </Flex>
            )}
            {error && (
              <Text size="1" color="red">
                {error}
              </Text>
            )}
          </Flex>
        )}

        {phase === "pick" && (
          <Flex direction="column" gap="2">
            <Text size="1" color="gray">
              Theorems in {repo}. Pick the ones to build a task from — their proofs and the helper
              lemmas only they use get cut.
            </Text>
            <Box style={{ maxHeight: 380, overflowY: "auto" }}>
              {options.map((o) => (
                <Flex
                  key={o.name}
                  gap="2"
                  px="2"
                  py="2"
                  className="ts-row"
                  onClick={() => toggle(o.name)}
                  style={{ borderBottom: "1px solid var(--gray-a3)", borderRadius: "var(--radius-2)" }}
                >
                  <Checkbox
                    checked={picked.has(o.name)}
                    mt="1"
                    style={{ pointerEvents: "none" }}
                  />
                  <Box style={{ minWidth: 0 }}>
                    <Text size="2" style={{ fontFamily: monoFont, display: "block" }}>
                      {o.name}
                    </Text>
                    <Text size="1" color="gray" style={{ fontStyle: "italic", display: "block" }}>
                      {o.gloss}
                    </Text>
                  </Box>
                </Flex>
              ))}
            </Box>
            {error && (
              <Text size="1" color="red">
                {error}
              </Text>
            )}
          </Flex>
        )}

        <Flex gap="3" mt="4" justify="end">
          {phase === "pick" ? (
            <>
              <Button variant="soft" color="gray" onClick={() => setPhase("form")} disabled={busy}>
                Back
              </Button>
              <Button onClick={() => create([...picked])} disabled={busy || picked.size === 0} highContrast>
                {busy ? "Starting" : `Build task (${picked.size})`}
              </Button>
            </>
          ) : (
            <>
              <Button variant="soft" color="gray" onClick={close}>
                Cancel
              </Button>
              <Button
                onClick={scan}
                disabled={phase === "scanning" || repo.trim().length < 3}
                highContrast
              >
                {phase === "scanning" ? "Scanning" : "Scan theorems"}
              </Button>
            </>
          )}
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
