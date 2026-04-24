import type { ModelPreset, ModelTestResult, ValidationResult } from '../types/api.js';

export type ValidationBadgeTone =
  | 'success'
  | 'warning'
  | 'danger'
  | 'muted';

export type ValidationGroup = {
  key: string;
  provider: string;
  base_url: string;
  results: ValidationResult[];
};

export type RetargetPreviewItem = {
  presetId: number;
  from: string;
  to: string;
};

export type ModelTestSummary = {
  tone: ValidationBadgeTone;
  title: string;
  details: string[];
};

const VALIDATION_BADGE_META: Record<string, { label: string; tone: ValidationBadgeTone }> = {
  available_exact: { label: 'Available', tone: 'success' },
  available_metadata_drift: { label: 'Drifted', tone: 'warning' },
  available_retarget_suggestion: { label: 'Renamed', tone: 'warning' },
  missing: { label: 'Missing', tone: 'danger' },
  server_unreachable: { label: 'Offline', tone: 'danger' },
  needs_probe: { label: 'Needs Probe', tone: 'muted' },
  validation_failed: { label: 'Validation Failed', tone: 'danger' },
};

export function getValidationBadgeMeta(status: string) {
  return VALIDATION_BADGE_META[status] || { label: status, tone: 'muted' as const };
}

export function groupValidationResults(results: ValidationResult[]): ValidationGroup[] {
  const groups = new Map<string, ValidationGroup>();

  for (const result of results) {
    const key = `${result.provider}::${result.base_url}`;
    const existing = groups.get(key);
    if (existing) {
      existing.results.push(result);
      continue;
    }
    groups.set(key, {
      key,
      provider: result.provider,
      base_url: result.base_url,
      results: [result],
    });
  }

  return Array.from(groups.values());
}

export function buildRetargetPreview(results: ValidationResult[], models: ModelPreset[]): RetargetPreviewItem[] {
  const modelsById = new Map(models.map((model) => [model.id, model]));

  return results
    .filter((result) => result.status === 'available_retarget_suggestion' && result.live_match?.model_id)
    .map((result) => ({
      presetId: result.preset_id,
      from: modelsById.get(result.preset_id)?.name || `Preset ${result.preset_id}`,
      to: result.live_match?.model_id || result.suggested_action || 'Unknown target',
    }));
}

export function getBulkArchivePresetIds(
  results: ValidationResult[],
  selectedPresetIds: Iterable<number>,
  mode: 'missing' | 'selected',
): number[] {
  if (mode === 'missing') {
    return results
      .filter((result) => result.status === 'missing')
      .map((result) => result.preset_id);
  }

  const selected = new Set(selectedPresetIds);
  return results
    .filter((result) => result.status === 'missing' && selected.has(result.preset_id))
    .map((result) => result.preset_id);
}

export function describeModelTestResult(result: ModelTestResult): ModelTestSummary {
  const details: string[] = [];

  if (result.ok) {
    if (result.validation_status === 'available_exact') {
      details.push('Exact runnable match confirmed.');
    } else if (result.validation_status) {
      details.push(`Validation: ${getValidationBadgeMeta(result.validation_status).label}.`);
    }
  }

  if (result.resolved_model_id) {
    details.push(`Resolved model ID: ${result.resolved_model_id}`);
  }

  if (result.reasoning_supported_levels?.length) {
    details.push(`Reasoning support: ${result.reasoning_supported_levels.join(', ')}`);
  }

  if (result.validation_message) {
    details.push(result.validation_message);
  } else if (result.message) {
    details.push(result.message);
  } else if (result.error) {
    details.push(result.error);
  }

  if (!result.ok && result.validation_status === 'validation_failed') {
    return {
      tone: 'danger',
      title: 'Validation failed',
      details,
    };
  }

  if (!result.ok) {
    return {
      tone: 'danger',
      title: result.reachable ? 'Model test failed' : 'Server unreachable',
      details,
    };
  }

  return {
    tone: 'success',
    title: 'Exact runnable',
    details,
  };
}
