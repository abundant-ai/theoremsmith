import { useEffect, useState } from "react";
import { Button, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";

import { api, type FileNode, type FilePreview } from "../api";
import { monoFont } from "../theme";

type Props = {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function TreeNode({ node, select }: { node: FileNode; select: (path: string) => void }) {
  if (node.type === "file") {
    return (
      <button
        type="button"
        onClick={() => select(node.path)}
        style={{
          display: "block",
          width: "100%",
          border: 0,
          background: "none",
          padding: "3px 6px",
          color: "var(--gray-12)",
          cursor: "pointer",
          fontFamily: monoFont,
          fontSize: 12,
          textAlign: "left",
        }}
      >
        {node.name}
      </button>
    );
  }
  return (
    <details open={node.path === "task" || node.path === "extension"}>
      <summary style={{ cursor: "pointer", padding: "3px 0", fontSize: 12 }}>{node.name}</summary>
      <div style={{ borderLeft: "1px solid var(--gray-a5)", marginLeft: 5, paddingLeft: 8 }}>
        {node.children?.map((child) => (
          <TreeNode key={child.path} node={child} select={select} />
        ))}
      </div>
    </details>
  );
}

export default function FileViewer({ runId, open, onOpenChange }: Props) {
  const [root, setRoot] = useState<FileNode | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    api
      .files(runId)
      .then(({ tree }) => setRoot(tree))
      .catch((e) => setError(String(e instanceof Error ? e.message : e)))
      .finally(() => setLoading(false));
  }, [open, runId]);

  async function select(path: string) {
    setLoading(true);
    setError("");
    try {
      setPreview(await api.file(runId, path));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content style={{ maxWidth: 1100 }}>
        <Dialog.Title>Task files</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Solver-visible task files and generated extensions. Grader and original solution files are
          hidden.
        </Dialog.Description>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr)",
            minHeight: 420,
            maxHeight: "70vh",
            border: "1px solid var(--gray-a5)",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          <div style={{ overflow: "auto", padding: 12, borderRight: "1px solid var(--gray-a5)" }}>
            {root?.children?.map((node) => (
              <TreeNode key={node.path} node={node} select={select} />
            ))}
          </div>
          <div style={{ overflow: "auto", padding: 16, background: "var(--gray-a2)" }}>
            {loading && !preview ? <Spinner size="2" /> : null}
            {error ? <Text color="red">{error}</Text> : null}
            {!preview && !loading && !error ? (
              <Text size="2" color="gray">
                Choose a file to view it.
              </Text>
            ) : null}
            {preview?.kind === "text" ? (
              <>
                <Text size="1" color="gray" as="div" mb="3" style={{ fontFamily: monoFont }}>
                  {preview.path}
                </Text>
                <pre
                  style={{
                    margin: 0,
                    fontFamily: monoFont,
                    fontSize: 12,
                    lineHeight: 1.55,
                    whiteSpace: "pre",
                  }}
                >
                  {preview.content}
                </pre>
              </>
            ) : null}
            {preview?.kind === "binary" ? <Text>This binary file cannot be previewed.</Text> : null}
            {preview?.kind === "too_large" ? (
              <Text>This file is too large to preview ({preview.size.toLocaleString()} bytes).</Text>
            ) : null}
          </div>
        </div>
        <Flex justify="end" mt="4">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Close
            </Button>
          </Dialog.Close>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
