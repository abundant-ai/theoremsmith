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
    slots?: number;
    deleted?: number;
    verified?: boolean;
    verify?: string;
    statements?: Record<string, string>;
  } | null;
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

export const api = {
  config: () => call<{ model: string; configured: boolean; max_runs: number }>("/config"),
  runs: () => call<{ runs: Run[] }>("/runs"),
  run: (id: string) => call<Run>(`/runs/${id}`),
  create: (repo: string, sha: string, goals: string[]) =>
    call<Run>("/runs", { method: "POST", body: JSON.stringify({ repo, sha, goals }) }),
  remove: (id: string) => call<{ deleted: string }>(`/runs/${id}`, { method: "DELETE" }),
  taskUrl: (id: string) => `/api/runs/${id}/task`,
};
