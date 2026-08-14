import { Flex, Spinner, Text } from "@radix-ui/themes";

import { STAGES, type StageState } from "../api";

const LABEL: Record<string, string> = {
  clone: "Clone",
  build: "Build",
  probe: "Probe",
  select: "Choose theorems",
  cut: "Cut proofs",
  emit: "Write task",
  verify: "Verify",
};

function Mark({ state }: { state: StageState }) {
  if (state === "running") return <Spinner size="1" />;
  const color =
    state === "done" ? "var(--green-9)" : state === "failed" ? "var(--red-9)" : "var(--gray-a6)";
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        display: "inline-block",
        flexShrink: 0,
      }}
    />
  );
}

export default function Stages({
  stages,
  oddish,
}: {
  stages: Record<string, StageState>;
  oddish?: StageState;
}) {
  const items: { key: string; label: string; state: StageState }[] = STAGES.map((name) => ({
    key: name,
    label: LABEL[name],
    state: stages[name] ?? "pending",
  }));
  if (oddish) items.push({ key: "oddish", label: "Run on Oddish", state: oddish });

  return (
    <Flex
      wrap="wrap"
      style={{
        border: "1px solid var(--gray-a4)",
        borderRadius: "var(--radius-4)",
        overflow: "hidden",
        background: "var(--gray-a1)",
      }}
    >
      {items.map((item, i) => (
        <Flex
          key={item.key}
          align="center"
          gap="2"
          px="3"
          py="2"
          style={{
            flex: "1 1 120px",
            minWidth: 0,
            borderLeft: i === 0 ? "none" : "1px solid var(--gray-a3)",
            opacity: item.state === "pending" ? 0.5 : 1,
          }}
        >
          <Mark state={item.state} />
          <Text size="1" truncate>
            {item.label}
          </Text>
        </Flex>
      ))}
    </Flex>
  );
}
