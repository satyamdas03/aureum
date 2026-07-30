import type { Certificate, DataFile, Example } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  health: () => fetchJson<{ status: string; version: string }>("/api/health"),
  signals: () => fetchJson<string[]>("/api/signals"),
  examples: () => fetchJson<Example[]>("/api/examples"),
  data: () => fetchJson<DataFile[]>("/api/data"),

  author: (prompt: string, model?: string, maxCorrectionAttempts?: number) =>
    fetchJson<{ yaml: string; rationale: string }>("/api/author", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        model,
        max_correction_attempts: maxCorrectionAttempts,
      }),
    }),

  backtest: (strategyYaml: string, dataPath: string) =>
    fetchJson<Certificate>("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ strategy_yaml: strategyYaml, data_path: dataPath }),
    }),

  reflect: (
    strategyYaml: string,
    dataPath: string,
    model?: string,
    maxAttempts?: number
  ) =>
    fetchJson<{
      success: boolean;
      attempts: number;
      yaml: string | null;
      certificate: Certificate | null;
      drafts: string[];
    }>("/api/reflect", {
      method: "POST",
      body: JSON.stringify({
        strategy_yaml: strategyYaml,
        data_path: dataPath,
        model,
        max_attempts: maxAttempts,
      }),
    }),
};
