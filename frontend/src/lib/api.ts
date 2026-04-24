import axios from 'axios';
import { clampModelSelection } from '../pages/questionBrowser/queryState.js';
import type {
  ModelPreset,
  BenchmarkRun,
  PromptSuite,
  SuiteImportPayload,
  Criterion,
  ValidationResult,
  ModelTestResult,
  ConcurrencySetting,
  QuestionBrowserDetailResponse,
  QuestionBrowserMatchMode,
  QuestionBrowserPickerFrequencyBand,
  QuestionBrowserPickerGuidanceResponse,
  QuestionBrowserSearchResponse,
} from '@/types/api';

// Use same-origin by default (production), or explicit VITE_API_URL for development
const viteEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
const API_BASE = viteEnv.VITE_API_URL || '';
const DEMO_MODE = viteEnv.VITE_DEMO_MODE === 'true';

async function fetchDemoJson<T>(file: string): Promise<T> {
  const base = viteEnv.BASE_URL || '/';
  const res = await fetch(`${base}demo-data/${file}`);
  return (await res.json()) as T;
}

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// --- Auth helpers ---
const API_KEY_STORAGE_KEY = 'bellmark_api_key';

export function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setStoredApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function clearStoredApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
}

// Attach stored API key to every request
api.interceptors.request.use((config) => {
  const key = getStoredApiKey();
  if (key) {
    config.headers['X-API-Key'] = key;
  }
  return config;
});

// On 401, clear stored key so the gate re-prompts
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearStoredApiKey();
      window.dispatchEvent(new Event('bellmark-auth-required'));
    }
    return Promise.reject(error);
  },
);

// Check if server requires auth (null = indeterminate / server unreachable)
export async function checkAuthRequired(): Promise<boolean | null> {
  try {
    const res = await api.get('/api/auth/check');
    return res.data.auth_required === true;
  } catch {
    return null;
  }
}

// Validate a key against the server
export async function validateApiKey(key: string): Promise<boolean> {
  try {
    const res = await api.get('/api/models/', {
      headers: { 'X-API-Key': key },
    });
    return res.status === 200;
  } catch {
    return false;
  }
}


export function shouldForceReloadForVersionMismatch(currentVersion: string | null | undefined, serverVersion: string | null | undefined): boolean {
  const current = (currentVersion ?? '').trim();
  const server = (serverVersion ?? '').trim();
  if (!current || !server) {
    return false;
  }
  return current !== server;
}

export function buildVersionReloadUrl(currentUrl: string, serverVersion: string): string {
  const url = new URL(currentUrl, 'http://local.invalid');
  url.searchParams.set('__reload', serverVersion);
  return `${url.pathname}${url.search}${url.hash}`;
}

export async function fetchServerVersion(): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      cache: 'no-store',
      headers: {
        'X-API-Key': getStoredApiKey() ?? '',
      },
    });
    if (!response.ok) {
      return null;
    }
    const data = await response.json() as { version?: unknown };
    return typeof data.version === 'string' ? data.version : null;
  } catch {
    return null;
  }
}

export type CoverageMode =
  | 'none'
  | 'strict_leaf_coverage'
  | 'compact_leaf_coverage'
  | 'group_coverage';

export interface CoverageLeaf {
  id: string;
  label: string;
  description?: string | null;
  aliases?: string[];
}

export interface CoverageGroup {
  id: string;
  label: string;
  leaves: CoverageLeaf[];
}

export interface CoverageSpec {
  version: string;
  groups: CoverageGroup[];
}

export interface CoverageSpecPreviewResponse {
  spec: CoverageSpec;
}

export function buildQuestionBrowserParams(params: {
  modelIds: number[];
  matchMode?: QuestionBrowserMatchMode;
  sourceRunId?: number | null;
  sourceQuestionId?: number | null;
  questionId?: number | null;
  limit?: number;
  offset?: number;
}) {
  const matchMode = params.matchMode ?? 'strict';
  const modelIds = clampModelSelection(params.modelIds);

  if (modelIds.length < 2) {
    throw new Error('question browser requires 2 to 15 models');
  }

  if (matchMode === 'strict' && params.sourceRunId == null) {
    throw new Error('sourceRunId is required for strict mode');
  }

  return {
    models: modelIds.join(','),
    match: matchMode,
    ...(params.sourceRunId != null ? { sourceRun: params.sourceRunId } : {}),
    ...(params.sourceQuestionId != null ? { sourceQuestion: params.sourceQuestionId } : {}),
    ...(params.questionId != null ? { question: params.questionId } : {}),
    ...(params.limit != null ? { limit: params.limit } : {}),
    ...(params.offset != null ? { offset: params.offset } : {}),
  };
}

// Models API
export const modelsApi = {
  list: (params?: { include_archived?: boolean }) =>
    api.get<ModelPreset[]>('/api/models/', { params }),
  create: (data: Record<string, unknown>) => api.post('/api/models/', data),
  get: (id: number) => api.get(`/api/models/${id}`),
  delete: (id: number) => api.delete(`/api/models/${id}`),
  test: (id: number) => api.post<ModelTestResult>(`/api/models/${id}/test`),
  validate: (data: { scope: 'local' | 'specific_ids'; provider?: string; base_url?: string; model_ids?: number[] }) =>
    api.post<ValidationResult[]>('/api/models/validate', data),
  update: (id: number, data: Partial<{
    name: string;
    provider: string;
    base_url: string;
    model_id: string;
    api_key: string;
    quantization: string | null;
    quantization_bits: number | null;
    model_format: string | null;
    model_source: string | null;
    parameter_count: string | null;
    selected_variant: string | null;
    model_architecture: string | null;
    context_limit: number | null;
    is_reasoning: boolean;
    reasoning_level: string | null;
  }>) => api.put(`/api/models/${id}`, data),
  discover: (data: { provider: string; base_url?: string; api_key?: string }) =>
    api.post('/api/models/discover', data),
};

// Benchmarks API
export const benchmarksApi = {
  list: () => api.get<BenchmarkRun[]>('/api/benchmarks/'),
  create: (data: Record<string, unknown>) => api.post('/api/benchmarks/', data),
  get: (id: number) => DEMO_MODE
    ? fetchDemoJson('benchmark.json').then(data => ({ data }))
    : api.get(`/api/benchmarks/${id}`),
  delete: (id: number) => api.delete(`/api/benchmarks/${id}`),
  cancel: (id: number) => api.post(`/api/benchmarks/${id}/cancel`),
  resume: (id: number) => api.post(`/api/benchmarks/${id}/resume`),
  retry: (id: number, itemType: string, itemId: number) =>
    api.post(`/api/benchmarks/${id}/retry/${itemType}/${itemId}`),
  export: (id: number, format: 'pptx' | 'pdf' | 'html' | 'json' | 'csv', theme?: 'light' | 'dark') => {
    if (DEMO_MODE) {
      // In demo mode, redirect to static sample files hosted on the parent site
      const themeLabel = theme ? `-${theme}` : '';
      const filename = `bellmark-analytical-reasoning${themeLabel}.${format}`;
      const url = `/samples/${filename}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.target = '_top';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => document.body.removeChild(a), 100);
      // Return a resolved promise with empty data to satisfy the caller
      return Promise.resolve({ data: new Blob() });
    }
    return api.get(`/api/benchmarks/${id}/export/${format}${theme ? `?theme=${theme}` : ''}`, { responseType: 'blob' });
  },
  compare: (ids: number[]) => api.get(`/api/benchmarks/compare?ids=${ids.join(',')}`),
  compareParent: (id: number) => api.get(`/api/benchmarks/${id}/compare-parent`),
  statistics: (id: number) => DEMO_MODE
    ? fetchDemoJson('statistics.json')
    : api.get(`/api/benchmarks/${id}/statistics`).then(r => r.data),
  bias: (id: number) => DEMO_MODE
    ? fetchDemoJson('bias.json')
    : api.get(`/api/benchmarks/${id}/bias`).then(r => r.data),
  calibration: (id: number) => DEMO_MODE
    ? fetchDemoJson('calibration.json')
    : api.get(`/api/benchmarks/${id}/calibration`).then(r => r.data),
  questionBrowserSearch: (params: {
    modelIds: number[];
    matchMode?: QuestionBrowserMatchMode;
    sourceRunId?: number | null;
    sourceQuestionId?: number | null;
    limit?: number;
    offset?: number;
  }) => api.get<QuestionBrowserSearchResponse>('/api/question-browser/search', {
    params: buildQuestionBrowserParams(params),
  }).then(r => r.data),
  questionBrowserDetail: (
    questionId: number,
    params: {
      modelIds: number[];
      matchMode?: QuestionBrowserMatchMode;
      sourceRunId?: number | null;
      sourceQuestionId?: number | null;
    },
  ) => api.get<QuestionBrowserDetailResponse>(`/api/question-browser/questions/${questionId}`, {
    params: buildQuestionBrowserParams(params),
  }).then(r => r.data),
  questionBrowserPickerGuidance: (params: {
    selectedModelIds?: number[];
    frequencyBand?: QuestionBrowserPickerFrequencyBand;
  } = {}) => api.get<QuestionBrowserPickerGuidanceResponse>('/api/question-browser/picker-guidance', {
    params: {
      ...(params.selectedModelIds != null ? { selected_model_ids: params.selectedModelIds.join(',') } : {}),
      ...(params.frequencyBand != null ? { frequency_band: params.frequencyBand } : {}),
    },
  }).then(r => r.data),
};

// Concurrency Settings API
export const concurrencyApi = {
  list: (): Promise<ConcurrencySetting[]> =>
    api.get('/api/concurrency-settings/').then(r => r.data.settings),
  update: (provider: string, base_url: string | null, max_concurrency: number | null) =>
    api.patch('/api/concurrency-settings/', { provider, base_url, max_concurrency }).then(r => r.data),
};

// Questions API
export const questionsApi = {
  generate: (data: {
    model_id: number;
    topic: string;
    count: number;
    system_context?: string;
    context_attachment_id?: number;
  }) => api.post('/api/questions/generate', data),
};

// Criteria API
export const criteriaApi = {
  generate: (modelId: number, topic: string, count: number = 4, questions: Array<{system_prompt: string; user_prompt: string; attachment_ids: number[]}> = [], globalAttachmentIds: number[] = []) =>
    api.post('/api/criteria/generate', { model_id: modelId, topic, count, questions, global_attachment_ids: globalAttachmentIds }),
};

// Suites API
export const suitesApi = {
  list: () => api.get<PromptSuite[]>('/api/suites/'),
  listPipelines: () => api.get<ActiveSuitePipelineSnapshot[]>('/api/suites/pipelines'),
  cancelPipeline: (sessionId: string) => api.post(`/api/suites/pipelines/${sessionId}/cancel`),
  parseCoverageOutline: (outline: string) => api.post<CoverageSpecPreviewResponse>('/api/suites/parse-coverage-outline', { outline }),
  create: (data: { name: string; description: string; items: { system_prompt: string; user_prompt: string }[] }) =>
    api.post('/api/suites/', data),
  get: (id: number) => api.get<PromptSuite>(`/api/suites/${id}`),
  update: (id: number, data: { name: string; description: string; items: { system_prompt: string; user_prompt: string; expected_answer?: string | null; category?: string | null; difficulty?: string | null; criteria?: Criterion[] | null }[]; default_criteria?: Criterion[] | null }) =>
    api.put(`/api/suites/${id}`, data),
  delete: (id: number) => api.delete(`/api/suites/${id}`),
  generate: (data: { name: string; model_id: number; topic: string; count: number; system_context?: string; context_attachment_id?: number }) =>
    api.post('/api/suites/generate', data),
  fromRun: (runId: number, data: { name: string; description?: string }) =>
    api.post(`/api/suites/from-run/${runId}`, data),
  importSuite: (data: SuiteImportPayload) => api.post('/api/suites/import', data),
  importSuiteFromUrl: (url: string) => api.post('/api/suites/import-url', { url }),
  exportSuiteUrl: (id: number) => `/api/suites/${id}/export`,
  generateV2: (data: {
    name: string;
    topic: string;
    count?: number;
    generator_model_id?: number;
    generator_model_ids?: number[];
    editor_model_id?: number | null;
    reviewer_model_ids?: number[];
    difficulty?: string;
    categories?: string[];
    generate_answers?: boolean;
    criteria_depth?: string;
    context_attachment_id?: number | null;
    coverage_mode?: CoverageMode;
    coverage_spec?: CoverageSpec | null;
    coverage_outline_text?: string | null;
    max_topics_per_question?: number;
  }) => api.post('/api/suites/generate-v2', data),
};

// Attachment types
export interface Attachment {
  id: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  [key: string]: unknown;
}

export interface SuiteAttachment {
  id: number;
  attachment_id: number;
  scope: 'all_questions' | 'specific';
  suite_item_order: number | null;
  attachment: Attachment;
}

export interface SuiteGenerationLogEntry {
  timestamp: number;
  level: 'info' | 'warning' | 'error';
  message: string;
}

export interface SuiteReviewerStatus {
  model: string;
  status: 'pending' | 'working' | 'done' | 'retry' | 'failed' | 'skipped';
  started_at?: number;
  elapsed_seconds?: number;
  attempt?: number;
  error?: string;
}

export interface ActiveGenerationCall {
  task_id: string;
  model: string;
  detail: string;
  started_at: number;
  question_count: number;
  generator_index: number;
  total_generators: number;
  generator_batch_index: number;
  generator_total_batches: number;
  global_batch_index: number;
  total_global_batches: number;
}

export interface ActiveReviewBatch {
  task_id: string;
  batch_index: number;
  total_batches: number;
  started_at: number;
  detail: string;
  reviewers_status: SuiteReviewerStatus[];
}

export interface ActiveMergeBatch {
  task_id: string;
  batch_index: number;
  total_batches: number;
  started_at: number;
  detail: string;
  model: string;
}

export interface ActiveSuitePipelineSnapshot {
  session_id: string;
  name: string;
  topic: string;
  phase: string;
  phase_index: number;
  total_phases: number;
  phases: string[];
  batch: number;
  total_batches: number;
  overall_percent: number;
  call_started_at: number | null;
  model: string | null;
  reviewers_status: SuiteReviewerStatus[] | null;
  questions_generated: number;
  questions_reviewed: number;
  questions_merged: number;
  question_count: number;
  completed_generation_batches: number;
  active_generation_batches: number;
  active_generation_calls: ActiveGenerationCall[];
  active_review_batches: ActiveReviewBatch[];
  active_merge_batches: ActiveMergeBatch[];
  coverage_mode?: string;
  required_leaf_count?: number;
  covered_leaf_count?: number;
  missing_leaf_count?: number;
  duplicate_cluster_count?: number;
  replacement_count?: number;
  generator: string;
  generators?: string[];
  editor?: string | null;
  reviewers: string[];
  difficulty?: string;
  categories?: string[];
  generate_answers?: boolean;
  criteria_depth?: string;
  elapsed_seconds: number;
  recent_log: SuiteGenerationLogEntry[];
}

// Attachments API
export const attachmentsApi = {
  list: () => api.get<Attachment[]>('/api/attachments/'),

  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<Attachment>('/api/attachments/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },

  get: (id: number) => api.get<Attachment>(`/api/attachments/${id}`),

  delete: (id: number) => api.delete(`/api/attachments/${id}`),

  // Suite attachment endpoints
  listSuiteAttachments: (suiteId: number) =>
    api.get<SuiteAttachment[]>(`/api/suites/${suiteId}/attachments`),

  addSuiteAttachment: (suiteId: number, data: {
    attachment_id: number;
    scope: 'all_questions' | 'specific';
    suite_item_order?: number;
  }) => api.post<SuiteAttachment>(`/api/suites/${suiteId}/attachments`, data),

  removeSuiteAttachment: (suiteId: number, attachmentId: number) =>
    api.delete(`/api/suites/${suiteId}/attachments/${attachmentId}`),
};

// ELO API
export const eloApi = {
  leaderboard: () => api.get('/api/elo/').then(r => r.data),
  history: (modelId: number) => api.get(`/api/elo/${modelId}/history`).then(r => r.data),
  aggregateLeaderboard: () => api.get('/api/elo/aggregate-leaderboard').then(r => r.data),
};
