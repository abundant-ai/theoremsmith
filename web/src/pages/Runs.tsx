import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Callout, Card, Flex, Table, Text } from "@radix-ui/themes";

import { api, type Example, type Run } from "../api";
import NewRunDialog from "../components/NewRunDialog";
import StatusChip from "../components/StatusChip";
import { monoFont } from "../theme";
import { since } from "../format";

export default function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [open, setOpen] = useState(false);
  const [initialRepo, setInitialRepo] = useState("");
  const [models, setModels] = useState("");
  const [examples, setExamples] = useState<Example[]>([]);
  const [configured, setConfigured] = useState(true);
  const navigate = useNavigate();

  const openWith = (repo: string) => {
    setInitialRepo(repo);
    setOpen(true);
  };

  useEffect(() => {
    api.config().then((c) => {
      setModels(`create ${c.create_model} · Oddish run ${c.oddish_agent} / ${c.oddish_model}`);
      setExamples(c.examples);
      setConfigured(c.configured);
    });
  }, []);

  useEffect(() => {
    let live = true;
    const tick = () => api.runs().then((r) => live && setRuns(r.runs)).catch(() => {});
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  return (
    <Flex direction="column" gap="4">
      {!configured && (
        <Callout.Root color="amber" variant="surface">
          <Callout.Text>
            THEOREMSMITH_API_KEY is not set on the server. Runs cannot start until it is.
          </Callout.Text>
        </Callout.Root>
      )}

      <Flex align="center" justify="between" gap="3" wrap="wrap">
        <Text size="1" color="gray">
          {models || " "}
        </Text>
        <Button onClick={() => openWith("")} disabled={!configured} highContrast>
          New run
        </Button>
      </Flex>

      {runs === null ? null : runs.length === 0 ? (
        <Card size="4">
          <Flex direction="column" align="center" gap="3" py="6">
            <Text size="2" color="gray">
              No runs yet. Point it at a Lean 4 repository and watch a proof task get built.
            </Text>
            {examples.length > 0 && (
              <>
                <Text size="1" color="gray">
                  or start from one of these
                </Text>
                <Flex gap="2" wrap="wrap" justify="center">
                  {examples.map((ex) => (
                    <Button
                      key={ex.repo}
                      variant="soft"
                      size="1"
                      onClick={() => openWith(ex.repo)}
                      disabled={!configured}
                      title={ex.note}
                      style={{ fontFamily: monoFont }}
                    >
                      {ex.repo}
                    </Button>
                  ))}
                </Flex>
              </>
            )}
          </Flex>
        </Card>
      ) : (
        <Table.Root variant="surface" size="1">
          <Table.Header>
            <Table.Row>
              <Table.ColumnHeaderCell>Repository</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Targets</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Status</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell justify="end">Updated</Table.ColumnHeaderCell>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {runs.map((run) => (
              <Table.Row
                key={run.id}
                className="ts-row"
                onClick={() => navigate(`/runs/${run.id}`)}
              >
                <Table.RowHeaderCell>
                  <Text size="2" weight="medium">
                    {run.repo}
                  </Text>
                </Table.RowHeaderCell>
                <Table.Cell>
                  <Text size="1" color="gray">
                    {run.result?.targets?.length ? run.result.targets.join(", ") : "—"}
                  </Text>
                </Table.Cell>
                <Table.Cell>
                  <StatusChip run={run} />
                </Table.Cell>
                <Table.Cell justify="end">
                  <Text size="1" color="gray">
                    {since(run.updated)}
                  </Text>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table.Root>
      )}

      <NewRunDialog
        open={open}
        onClose={() => setOpen(false)}
        onCreated={(run) => navigate(`/runs/${run.id}`)}
        examples={examples}
        initialRepo={initialRepo}
      />
    </Flex>
  );
}
