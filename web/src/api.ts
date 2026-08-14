export type StageState = "pending" | "running" | "done" | "failed";

export const STAGES = ["clone", "build", "probe", "select", "cut", "emit", "verify"] as const;

export type Run = {
  id: string;
  repo: string;
  sha: string;
  goals: string[];
  status: "queued" | "running" | "done" | "failed";
  stage: string | null;
  stages: Record<string, StageState>;
  error: string | null;
  created: number;
  updated: number;
  result: {
    slug?: string;
    targets?: string[];
    support?: number;
    slots?: number;
    verified?: boolean;
    verify?: string;
    statements?: Record<string, string>;
    glosses?: Record<string, string>;
    oddish?: OddishRun;
    oddish_error?: string;
    extension?: SyntheticExtension;
  } | null;
};

export type SyntheticExtension = {
  status: "running" | "done" | "failed";
  file?: string;
  theorems?: string[];
  depends_on?: string;
  summary?: string;
  error?: string;
};

export type FileNode = {
  name: string;
  path: string;
  type: "dir" | "file";
  size?: number;
  children?: FileNode[];
};

export type FilePreview = {
  kind: "text" | "binary" | "too_large";
  name: string;
  path: string;
  size: number;
  content?: string;
};

export type OddishRun = {
  public_url: string;
  experiment_url?: string;
  experiment?: string;
  agent?: string;
  model?: string;
};

export type Event = {
  seq: number;
  t: number;
  kind: "log" | "stage" | "status" | "model" | "delta" | "end";
  text?: string;
  level?: string;
  stage?: string;
  state?: StageState | "start" | "end";
  status?: string;
  phase?: string;
  error?: string;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json() as Promise<T>;
}

export type Example = { repo: string; note: string };

export type Config = {
  create_model: string;
  configured: boolean;
  max_runs: number;
  examples: Example[];
  oddish_agent: string;
  oddish_model: string;
  oddish_timeout: number;
  oddish_available: boolean;
};

export type ScanOption = { name: string; file: string; gloss: string };

export const api = {
  config: () => call<Config>("/config"),
  runs: () => call<{ runs: Run[] }>("/runs"),
  run: (id: string) => call<Run>(`/runs/${id}`),
  scan: (repo: string, sha: string) =>
    call<{ repo: string; options: ScanOption[] }>("/scan", {
      method: "POST",
      body: JSON.stringify({ repo, sha }),
    }),
  scanStreamUrl: (repo: string, sha: string) =>
    `/api/scan/stream?repo=${encodeURIComponent(repo)}&sha=${encodeURIComponent(sha)}`,
  create: (repo: string, sha: string, goals: string[], glosses: Record<string, string> = {}) =>
    call<Run>("/runs", { method: "POST", body: JSON.stringify({ repo, sha, goals, glosses }) }),
  submit: (id: string) => call<{ submitting: boolean }>(`/runs/${id}/submit`, { method: "POST" }),
  extend: (id: string) => call<{ generating: boolean }>(`/runs/${id}/extend`, { method: "POST" }),
  files: (id: string) => call<{ tree: FileNode }>(`/runs/${id}/files`),
  file: (id: string, path: string) =>
    call<FilePreview>(`/runs/${id}/file?path=${encodeURIComponent(path)}`),
  remove: (id: string) => call<{ deleted: string }>(`/runs/${id}`, { method: "DELETE" }),
  taskUrl: (id: string) => `/api/runs/${id}/task`,
};
