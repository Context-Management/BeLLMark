export type TemperatureMode = 'normalized' | 'provider_default' | 'custom';

const TEMPERATURE_COPY: Record<TemperatureMode, { label: string; description: string }> = {
  normalized: {
    label: 'Normalized (Best-effort)',
    description:
      'Best-effort provider/model normalization for benchmarks. Some reasoning models still ignore or override temperature.',
  },
  provider_default: {
    label: 'Recommended Defaults (Best-effort)',
    description:
      'Uses model-specific recommendations when available, otherwise falls back to provider defaults.',
  },
  custom: {
    label: 'Custom per Model',
    description: 'Uses custom temperature set on each model preset (falls back to normalized if not set).',
  },
};

export function getTemperatureModeLabel(mode: TemperatureMode): string {
  return TEMPERATURE_COPY[mode].label;
}

export function getTemperatureModeDescription(mode: TemperatureMode): string {
  return TEMPERATURE_COPY[mode].description;
}

export function getCustomTemperatureHelpText(): string {
  return 'Used when "Custom per Model" temperature mode is selected (0.0-2.0)';
}
