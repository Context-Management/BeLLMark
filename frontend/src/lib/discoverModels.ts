export type DiscoverSort = 'default' | 'az' | 'za';
export type DiscoverCapability = 'all' | 'vision' | 'reasoning';

export type DiscoveredModel = {
  model: string;
  name?: string;
  model_id?: string;
  provider_default_url?: string;
  is_reasoning?: boolean;
  reasoning_level?: string;
  supports_vision?: boolean;
  context_limit?: number;
  price_input?: number;
  price_output?: number;
  price_source?: string;
  price_source_url?: string;
  price_checked_at?: string;
  price_currency?: string;
  quantization?: string;
  quantization_bits?: number;
  parameter_count?: string;
  selected_variant?: string;
  model_architecture?: string;
  model_format?: string;
  model_source?: string;
  supported_reasoning_levels?: string[];
  reasoning_detection_source?: string;
};

export type IndexedDiscoveredModel = DiscoveredModel & { _origIndex: number };

export function filterDiscoveredModels(
  models: DiscoveredModel[],
  options: {
    searchTerm: string;
    sort: DiscoverSort;
    capability: DiscoverCapability;
    selectedOnly: boolean;
    selectedIndices: Set<number>;
  },
): IndexedDiscoveredModel[] {
  const { searchTerm, sort, capability, selectedOnly, selectedIndices } = options;

  let result = models.map((m, i) => ({ ...m, _origIndex: i }));

  if (selectedOnly) {
    result = result.filter((m) => selectedIndices.has(m._origIndex));
  }

  if (capability === 'vision') {
    result = result.filter((m) => m.supports_vision);
  } else if (capability === 'reasoning') {
    result = result.filter((m) => m.is_reasoning);
  }

  const term = searchTerm.trim().toLowerCase();
  if (term) {
    result = result.filter((m) => {
      const haystack = [
        m.name || '',
        m.model_id || m.model || '',
        m.model || '',
        m.parameter_count || '',
        m.selected_variant || '',
        m.model_architecture || '',
        m.quantization_bits != null ? String(m.quantization_bits) : '',
        m.supports_vision ? 'vision image multimodal' : '',
        m.is_reasoning ? `reasoning ${m.reasoning_level || ''} thinking` : '',
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(term);
    });
  }

  if (sort !== 'default') {
    result.sort((a, b) => {
      const aKey = (a.name || a.model_id || a.model || '').toLowerCase();
      const bKey = (b.name || b.model_id || b.model || '').toLowerCase();
      return sort === 'az' ? aKey.localeCompare(bKey) : bKey.localeCompare(aKey);
    });
  }

  return result;
}
