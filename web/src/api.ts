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
    oddish?: OddishRun;
    oddish_error?: string;
  } | null;
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
  create: (repo: string, sha: string, goals: string[]) =>
    call<Run>("/runs", { method: "POST", body: JSON.stringify({ repo, sha, goals }) }),
  submit: (id: string) => call<{ submitting: boolean }>(`/runs/${id}/submit`, { method: "POST" }),
  remove: (id: string) => call<{ deleted: string }>(`/runs/${id}`, { method: "DELETE" }),
  taskUrl: (id: string) => `/api/runs/${id}/task`,
};
