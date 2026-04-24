import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { modelsApi, concurrencyApi } from '@/lib/api';
import {
  buildRetargetPreview,
  describeModelTestResult,
  getBulkArchivePresetIds,
  getValidationBadgeMeta,
  groupValidationResults,
  type RetargetPreviewItem,
} from '@/lib/modelValidation';
import {
  filterDiscoveredModels,
  type DiscoverCapability,
  type DiscoverSort,
  type DiscoveredModel,
} from '@/lib/discoverModels';
import { formatPricingUnitLabel, getModelPricingBadges } from '@/lib/modelPricingBadges';
import { getReasoningBadgeLabel } from '@/lib/reasoningBadge';
import { getHostLabel } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Eye, Brain, LayoutGrid, List, Plus, Pencil, Trash2, Play, Check, X, Loader2, Search, Archive, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import { ProviderLogo } from '@/components/ui/provider-logo';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { ErrorBanner } from '@/components/ui/error-banner';
import { getCustomTemperatureHelpText } from '@/lib/temperatureCopy';
import type { ModelPreset, ModelTestResult, ValidationResult, ConcurrencySetting } from '@/types/api';

type SortField = 'name' | 'provider' | 'model_id' | 'created_at';
type SortDirection = 'asc' | 'desc';

const PROVIDERS = [
  { value: 'lmstudio', label: 'LM Studio', defaultUrl: 'http://localhost:1234/v1/chat/completions' },
  { value: 'openai', label: 'OpenAI', defaultUrl: 'https://api.openai.com/v1/chat/completions' },
  { value: 'anthropic', label: 'Anthropic', defaultUrl: 'https://api.anthropic.com/v1/messages' },
  { value: 'google', label: 'Google', defaultUrl: 'https://generativelanguage.googleapis.com/v1beta/models' },
  { value: 'mistral', label: 'Mistral', defaultUrl: 'https://api.mistral.ai/v1/chat/completions' },
  { value: 'deepseek', label: 'DeepSeek', defaultUrl: 'https://api.deepseek.com/v1/chat/completions' },
  { value: 'grok', label: 'Grok', defaultUrl: 'https://api.x.ai/v1/chat/completions' },
  { value: 'glm', label: 'GLM', defaultUrl: 'https://open.bigmodel.cn/api/paas/v4/chat/completions' },
  { value: 'kimi', label: 'Kimi (Moonshot)', defaultUrl: 'https://api.moonshot.ai/v1/chat/completions' },
  { value: 'openrouter', label: 'OpenRouter', defaultUrl: 'https://openrouter.ai/api/v1/chat/completions' },
  { value: 'ollama', label: 'Ollama', defaultUrl: 'http://localhost:11434/v1/chat/completions' },
];

const SORT_OPTIONS = [
  { value: 'name-asc', label: 'Name (A-Z)' },
  { value: 'name-desc', label: 'Name (Z-A)' },
  { value: 'provider-asc', label: 'Provider (A-Z)' },
  { value: 'provider-desc', label: 'Provider (Z-A)' },
  { value: 'created_at-desc', label: 'Newest first' },
  { value: 'created_at-asc', label: 'Oldest first' },
];

const PRICING_BADGE_TONE_CLASSES = {
  input: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  output: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  source: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
} as const;

const VALIDATION_BADGE_CLASSNAMES = {
  success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  warning: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  danger: 'bg-red-500/15 text-red-300 border-red-500/30',
  muted: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
} as const;

const TEST_RESULT_PANEL_CLASSNAMES = {
  success: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-100',
  warning: 'border-amber-500/20 bg-amber-500/5 text-amber-100',
  danger: 'border-red-500/20 bg-red-500/5 text-red-100',
  muted: 'border-slate-500/20 bg-slate-500/5 text-slate-100',
} as const;

function PricingBadgesRow({
  model,
  className = '',
  badgeClassName = '',
}: {
  model: Pick<ModelPreset, 'price_input' | 'price_output' | 'price_currency' | 'price_source' | 'price_source_url' | 'price_checked_at'>;
  className?: string;
  badgeClassName?: string;
}) {
  const badges = getModelPricingBadges(model);

  if (badges.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1 ${className}`.trim()}>
      {badges.map((badge) => {
        const badgeNode = (
          <Badge
            variant="secondary"
            title={badge.title}
            className={`text-xs ${PRICING_BADGE_TONE_CLASSES[badge.tone]} ${badgeClassName}`.trim()}
          >
            {badge.label}
          </Badge>
        );

        if (!badge.href) {
          return <div key={badge.key}>{badgeNode}</div>;
        }

        return (
          <a key={badge.key} href={badge.href} title={badge.title} target="_blank" rel="noreferrer">
            {badgeNode}
          </a>
        );
      })}
    </div>
  );
}

type CompactModelMetadataSource = {
  model_id?: string;
  parameter_count?: string | null;
  quantization_bits?: number | null;
  selected_variant?: string | null;
  model_architecture?: string | null;
  context_limit?: number | null;
};

function formatQuantizationBits(bits: number): string {
  return Number.isInteger(bits) ? `${bits}-bit` : `${bits.toFixed(1)}-bit`;
}

function getCompactModelMetadata(model: CompactModelMetadataSource) {
  const metadata: Array<{ key: string; label: string; title?: string }> = [];

  if (model.parameter_count) {
    metadata.push({ key: 'parameter_count', label: model.parameter_count, title: 'Parameter count' });
  }

  if (model.quantization_bits != null) {
    metadata.push({ key: 'quantization_bits', label: formatQuantizationBits(model.quantization_bits), title: 'Quantization bits per weight' });
  }

  if (model.model_architecture) {
    metadata.push({ key: 'model_architecture', label: model.model_architecture, title: 'Model architecture' });
  }

  if (model.selected_variant && model.selected_variant !== model.model_id) {
    metadata.push({ key: 'selected_variant', label: model.selected_variant, title: 'Selected variant' });
  }

  if (model.context_limit) {
    metadata.push({ key: 'context_limit', label: `${(model.context_limit / 1000).toFixed(0)}K ctx`, title: 'Context window' });
  }

  return metadata;
}

function CompactModelMetadataRow({
  model,
  className = '',
}: {
  model: CompactModelMetadataSource;
  className?: string;
}) {
  const metadata = getCompactModelMetadata(model);
  if (metadata.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`.trim()}>
      {metadata.map((item) => (
        <span
          key={item.key}
          title={item.title}
          className="inline-flex items-center rounded bg-slate-100 dark:bg-slate-700/40 px-1.5 py-0.5 text-[11px] text-slate-600 dark:text-slate-300"
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}

function ValidationStatusBadge({ status }: { status: string }) {
  const meta = getValidationBadgeMeta(status);
  return (
    <Badge variant="secondary" className={`text-xs ${VALIDATION_BADGE_CLASSNAMES[meta.tone]}`}>
      {meta.label}
    </Badge>
  );
}

function ModelTestResultPanel({ result }: { result: ModelTestResult }) {
  const summary = describeModelTestResult(result);

  return (
    <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${TEST_RESULT_PANEL_CLASSNAMES[summary.tone]}`}>
      <div className="font-medium">{summary.title}</div>
      <div className="mt-1 space-y-1 text-slate-200/90">
        {summary.details.map((detail, index) => (
          <div key={`${summary.title}-${index}`}>{detail}</div>
        ))}
      </div>
    </div>
  );
}

export function Models() {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    provider: 'lmstudio',
    base_url: PROVIDERS[0].defaultUrl,
    model_id: '',
    api_key: '',
    price_input: '' as string | number,
    price_output: '' as string | number,
    price_currency: null as string | null,
    supports_vision: null as boolean | null,
    context_limit: '',
    is_reasoning: false,
    reasoning_level: '' as string,
    custom_temperature: '' as string | number,
  });
  const [testStatus, setTestStatus] = useState<Record<number, string>>({});
  const [testResults, setTestResults] = useState<Record<number, ModelTestResult | null>>({});
  const [validationResults, setValidationResults] = useState<ValidationResult[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isValidatingLocal, setIsValidatingLocal] = useState(false);
  const [activeValidationGroups, setActiveValidationGroups] = useState<Set<string>>(new Set());
  const [selectedMissingPresetIds, setSelectedMissingPresetIds] = useState<Set<number>>(new Set());
  const [retargetPreview, setRetargetPreview] = useState<RetargetPreviewItem[]>([]);
  const [isRetargetDialogOpen, setIsRetargetDialogOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<ModelPreset | null>(null);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; id: number | null }>({
    open: false,
    id: null
  });

  // Discovery state
  const [isDiscoverOpen, setIsDiscoverOpen] = useState(false);
  const [discoverProvider, setDiscoverProvider] = useState('lmstudio');
  const [discoverUrl, setDiscoverUrl] = useState('http://localhost:1234');
  const [discoverKey, setDiscoverKey] = useState('');
  const [discoveredModels, setDiscoveredModels] = useState<DiscoveredModel[]>([]);
  const [selectedDiscovered, setSelectedDiscovered] = useState<Set<number>>(new Set());
  const [isScanning, setIsScanning] = useState(false);
  const [discoverSearch, setDiscoverSearch] = useState('');
  const [discoverSort, setDiscoverSort] = useState<DiscoverSort>('default');
  const [discoverCapability, setDiscoverCapability] = useState<DiscoverCapability>('all');
  const [discoverShowSelectedOnly, setDiscoverShowSelectedOnly] = useState(false);

  const filteredDiscoveredModels = useMemo(() => {
    return filterDiscoveredModels(discoveredModels, {
      searchTerm: discoverSearch,
      sort: discoverSort,
      capability: discoverCapability,
      selectedOnly: discoverShowSelectedOnly,
      selectedIndices: selectedDiscovered,
    });
  }, [
    discoveredModels,
    discoverSearch,
    discoverSort,
    discoverCapability,
    discoverShowSelectedOnly,
    selectedDiscovered,
  ]);

  const hasDiscoverFilters = useMemo(
    () => Boolean(discoverSearch.trim()) || discoverCapability !== 'all' || discoverShowSelectedOnly,
    [discoverSearch, discoverCapability, discoverShowSelectedOnly],
  );

  // Filter and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [sortOption, setSortOption] = useState('name-asc');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [editFormData, setEditFormData] = useState({
    name: '',
    provider: 'lmstudio',
    base_url: '',
    model_id: '',
    api_key: '',
    price_input: '' as string | number,
    price_output: '' as string | number,
    price_currency: null as string | null,
    supports_vision: null as boolean | null,
    context_limit: '',
    is_reasoning: false,
    reasoning_level: '' as string,
    custom_temperature: '' as string | number,
    quantization: null as string | null,
    model_format: null as string | null,
    model_source: null as string | null,
  });

  const { data: models = [], isLoading, error, refetch } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const res = await modelsApi.list();
      return res.data;
    },
  });

  const { data: concurrencySettings = [] } = useQuery<ConcurrencySetting[]>({
    queryKey: ['concurrency-settings'],
    queryFn: () => concurrencyApi.list(),
  });

  const concurrencyMutation = useMutation({
    mutationFn: ({ provider, base_url, max_concurrency }: { provider: string; base_url: string | null; max_concurrency: number | null }) =>
      concurrencyApi.update(provider, base_url, max_concurrency),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['concurrency-settings'] });
    },
    onError: () => {
      toast.error('Failed to update concurrency setting');
    },
  });

  // Filter and sort models
  const filteredModels = useMemo(() => {
    let result = [...models] as ModelPreset[];

    // Apply search filter
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(
        (m) =>
          m.name.toLowerCase().includes(term) ||
          m.model_id.toLowerCase().includes(term)
      );
    }

    // Apply provider filter
    if (providerFilter !== 'all') {
      result = result.filter((m) => m.provider === providerFilter);
    }

    // Apply sorting
    const [field, direction] = sortOption.split('-') as [SortField, SortDirection];
    result.sort((a, b) => {
      let comparison = 0;
      if (field === 'created_at') {
        comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      } else {
        comparison = (a[field] || '').localeCompare(b[field] || '');
      }
      return direction === 'desc' ? -comparison : comparison;
    });

    return result;
  }, [models, searchTerm, providerFilter, sortOption]);

  // Get unique providers from current models for filter dropdown
  const availableProviders = useMemo(() => {
    const providers = new Set(models.map((m: ModelPreset) => m.provider));
    return PROVIDERS.filter((p) => providers.has(p.value));
  }, [models]);

  const validationGroups = useMemo(
    () => groupValidationResults(validationResults),
    [validationResults],
  );

  const modelsById = useMemo(
    () => new Map(models.map((model: ModelPreset) => [model.id, model])),
    [models],
  );

  const missingArchiveIds = useMemo(
    () => getBulkArchivePresetIds(validationResults, selectedMissingPresetIds, 'missing'),
    [validationResults, selectedMissingPresetIds],
  );

  const selectedArchiveIds = useMemo(
    () => getBulkArchivePresetIds(validationResults, selectedMissingPresetIds, 'selected'),
    [validationResults, selectedMissingPresetIds],
  );

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => modelsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      closeDialog();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => modelsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => modelsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      closeEditDialog();
    },
  });

  const retargetMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => modelsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
    },
  });

  const closeDialog = () => {
    setIsOpen(false);
    setFormData({
      name: '',
      provider: 'lmstudio',
      base_url: PROVIDERS[0].defaultUrl,
      model_id: '',
      api_key: '',
      price_input: '',
      price_output: '',
      price_currency: null,
      supports_vision: null,
      context_limit: '',
      is_reasoning: false,
      reasoning_level: '',
      custom_temperature: '',
    });
  };

  const handleProviderChange = (provider: string) => {
    const providerConfig = PROVIDERS.find(p => p.value === provider);
    setFormData({
      ...formData,
      provider,
      base_url: providerConfig?.defaultUrl || '',
      price_currency: null,
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Convert pricing to numbers or null
    const submitData = {
      ...formData,
      price_input: formData.price_input !== '' ? Number(formData.price_input) : null,
      price_output: formData.price_output !== '' ? Number(formData.price_output) : null,
      context_limit: formData.context_limit !== '' ? parseInt(formData.context_limit) : null,
      reasoning_level: formData.is_reasoning && formData.reasoning_level ? formData.reasoning_level : null,
      custom_temperature: formData.custom_temperature !== '' ? Number(formData.custom_temperature) : null,
    };
    createMutation.mutate(submitData);
  };

  const handleDelete = (id: number) => {
    setDeleteConfirm({ open: true, id });
  };

  const archivePresets = async (presetIds: number[]) => {
    if (presetIds.length === 0) return;

    await Promise.all(presetIds.map((presetId) => deleteMutation.mutateAsync(presetId)));
    setValidationResults((current) => current.filter((result) => !presetIds.includes(result.preset_id)));
    setSelectedMissingPresetIds((current) => {
      const next = new Set(current);
      for (const presetId of presetIds) next.delete(presetId);
      return next;
    });
    await queryClient.invalidateQueries({ queryKey: ['models'] });
  };

  const handleValidateLocal = async () => {
    setIsValidatingLocal(true);
    setValidationError(null);
    try {
      const response = await modelsApi.validate({ scope: 'local' });
      setValidationResults(response.data);
      setActiveValidationGroups(new Set(groupValidationResults(response.data).map((group) => group.key)));
      setSelectedMissingPresetIds(new Set(getBulkArchivePresetIds(response.data, [], 'missing')));
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = e?.response?.data?.detail || e?.message || 'Unknown error';
      setValidationError(message);
      toast.error(`Validate Local failed: ${message}`);
    } finally {
      setIsValidatingLocal(false);
    }
  };

  const toggleValidationGroup = (groupKey: string) => {
    setActiveValidationGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  };

  const toggleMissingSelection = (presetId: number, checked: boolean) => {
    setSelectedMissingPresetIds((current) => {
      const next = new Set(current);
      if (checked) next.add(presetId);
      else next.delete(presetId);
      return next;
    });
  };

  const openRetargetDialog = (result: ValidationResult) => {
    const preview = buildRetargetPreview([result], models);
    if (preview.length === 0) {
      toast.error('Retarget preview is unavailable for this result.');
      return;
    }
    setRetargetPreview(preview);
    setIsRetargetDialogOpen(true);
  };

  const handleConfirmRetarget = async () => {
    const previewById = new Map(retargetPreview.map((item) => [item.presetId, item]));
    const resultsToApply = validationResults.filter((result) => previewById.has(result.preset_id));

    for (const result of resultsToApply) {
      const liveMatch = result.live_match;
      if (!liveMatch?.model_id) continue;

      const updateData: Record<string, unknown> = { model_id: liveMatch.model_id };
      if (liveMatch.quantization !== undefined) updateData.quantization = liveMatch.quantization ?? null;
      if (liveMatch.quantization_bits !== undefined) updateData.quantization_bits = liveMatch.quantization_bits ?? null;
      if (liveMatch.model_format !== undefined) updateData.model_format = liveMatch.model_format ?? null;
      if (liveMatch.model_source !== undefined) updateData.model_source = liveMatch.model_source ?? null;
      if (liveMatch.parameter_count !== undefined) updateData.parameter_count = liveMatch.parameter_count ?? null;
      if (liveMatch.selected_variant !== undefined) updateData.selected_variant = liveMatch.selected_variant ?? null;
      if (liveMatch.model_architecture !== undefined) updateData.model_architecture = liveMatch.model_architecture ?? null;
      if (liveMatch.context_limit !== undefined) updateData.context_limit = liveMatch.context_limit ?? null;
      if (liveMatch.is_reasoning !== undefined) updateData.is_reasoning = liveMatch.is_reasoning;
      if (liveMatch.reasoning_level !== undefined) updateData.reasoning_level = liveMatch.reasoning_level ?? null;

      await retargetMutation.mutateAsync({ id: result.preset_id, data: updateData });
    }

    setIsRetargetDialogOpen(false);
    setRetargetPreview([]);
    await handleValidateLocal();
    toast.success('Retargeted local preset metadata.');
  };

  const handleTest = async (id: number) => {
    setTestStatus((current) => ({ ...current, [id]: 'testing' }));
    setTestResults((current) => ({ ...current, [id]: null }));
    try {
      const response = await modelsApi.test(id);
      setTestResults((current) => ({ ...current, [id]: response.data }));
      setTestStatus((current) => ({ ...current, [id]: response.data.ok ? 'success' : 'failed' }));
    } catch (err: unknown) {
      const model = modelsById.get(id);
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = e?.response?.data?.detail || e?.message || 'Unknown error';
      setTestResults((current) => ({
        ...current,
        [id]: {
          status: 'error',
          ok: false,
          reachable: false,
          provider: model?.provider || 'unknown',
          base_url: model?.base_url || '',
          model_id: model?.model_id || '',
          metadata_drift: [],
          error: message,
          message,
        },
      }));
      setTestStatus((current) => ({ ...current, [id]: 'failed' }));
    }
  };

  const openEditDialog = (model: ModelPreset) => {
    setEditingModel(model);
    setEditFormData({
      name: model.name,
      provider: model.provider,
      base_url: model.base_url,
      model_id: model.model_id,
      api_key: '',
      price_input: model.price_input ?? '',
      price_output: model.price_output ?? '',
      price_currency: model.price_currency ?? null,
      supports_vision: model.supports_vision ?? null,
      context_limit: model.context_limit?.toString() ?? '',
      is_reasoning: model.is_reasoning ?? false,
      reasoning_level: model.reasoning_level ?? '',
      custom_temperature: model.custom_temperature ?? '',
      quantization: model.quantization ?? null,
      model_format: model.model_format ?? null,
      model_source: model.model_source ?? null,
    });
    setIsEditOpen(true);
  };

  const closeEditDialog = () => {
    setIsEditOpen(false);
    setEditingModel(null);
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingModel) return;

    const updateData: Record<string, unknown> = {};
    if (editFormData.name !== editingModel.name) updateData.name = editFormData.name;
    if (editFormData.provider !== editingModel.provider) updateData.provider = editFormData.provider;
    if (editFormData.base_url !== editingModel.base_url) updateData.base_url = editFormData.base_url;
    if (editFormData.model_id !== editingModel.model_id) updateData.model_id = editFormData.model_id;
    if (editFormData.api_key) updateData.api_key = editFormData.api_key;
    // Handle pricing - convert to number or null
    const newPriceInput = editFormData.price_input !== '' ? Number(editFormData.price_input) : null;
    const newPriceOutput = editFormData.price_output !== '' ? Number(editFormData.price_output) : null;
    if (newPriceInput !== editingModel.price_input) updateData.price_input = newPriceInput;
    if (newPriceOutput !== editingModel.price_output) updateData.price_output = newPriceOutput;
    // Handle vision support
    if (editFormData.supports_vision !== editingModel.supports_vision) {
      updateData.supports_vision = editFormData.supports_vision;
    }
    // Handle context limit
    const newContextLimit = editFormData.context_limit !== '' ? parseInt(editFormData.context_limit) : null;
    if (newContextLimit !== editingModel.context_limit) updateData.context_limit = newContextLimit;
    // Handle reasoning
    if (editFormData.is_reasoning !== editingModel.is_reasoning) updateData.is_reasoning = editFormData.is_reasoning;
    const newReasoningLevel = editFormData.is_reasoning && editFormData.reasoning_level ? editFormData.reasoning_level : null;
    if (newReasoningLevel !== editingModel.reasoning_level) updateData.reasoning_level = newReasoningLevel;
    // Handle custom temperature
    const newCustomTemp = editFormData.custom_temperature !== '' ? Number(editFormData.custom_temperature) : null;
    if (newCustomTemp !== editingModel.custom_temperature) updateData.custom_temperature = newCustomTemp;
    // Handle quant metadata
    if (editFormData.quantization !== editingModel.quantization) updateData.quantization = editFormData.quantization;
    if (editFormData.model_format !== editingModel.model_format) updateData.model_format = editFormData.model_format;
    if (editFormData.model_source !== editingModel.model_source) updateData.model_source = editFormData.model_source;

    updateMutation.mutate({ id: editingModel.id, data: updateData });
  };

  const handleEditProviderChange = (provider: string) => {
    const providerConfig = PROVIDERS.find(p => p.value === provider);
    setEditFormData({
      ...editFormData,
      provider,
      base_url: providerConfig?.defaultUrl || editFormData.base_url,
      price_currency: null,
    });
  };

  const handleScan = async () => {
    setIsScanning(true);
    setDiscoveredModels([]);
    setSelectedDiscovered(new Set());
    setDiscoverSearch('');
    setDiscoverSort('default');
    setDiscoverCapability('all');
    setDiscoverShowSelectedOnly(false);
    try {
      const res = await modelsApi.discover({
        provider: discoverProvider,
        base_url: (discoverProvider === 'lmstudio' || discoverProvider === 'ollama') ? discoverUrl : undefined,
        api_key: discoverKey || undefined,
      });
      setDiscoveredModels(res.data);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(`Scan failed: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`);
    } finally {
      setIsScanning(false);
    }
  };

  const handleAddDiscovered = async () => {
    const provider = PROVIDERS.find(p => p.value === discoverProvider);
    const toAdd = discoveredModels.filter((_, i) => selectedDiscovered.has(i));

    let added = 0;
    try {
      for (const model of toAdd) {
        await modelsApi.create({
          name: model.name,
          provider: discoverProvider,
          base_url: model.provider_default_url || provider?.defaultUrl || '',
          model_id: model.model_id,
          is_reasoning: model.is_reasoning,
          reasoning_level: model.reasoning_level,
          supports_vision: model.supports_vision,
          context_limit: model.context_limit,
          price_input: model.price_input,
          price_output: model.price_output,
          price_source: model.price_source,
          price_source_url: model.price_source_url,
          price_checked_at: model.price_checked_at,
          price_currency: model.price_currency,
          quantization: model.quantization,
          quantization_bits: model.quantization_bits,
          model_format: model.model_format,
          model_source: model.model_source,
          parameter_count: model.parameter_count,
          selected_variant: model.selected_variant,
          model_architecture: model.model_architecture,
          reasoning_detection_source: model.reasoning_detection_source,
        });
        added += 1;
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = e?.response?.data?.detail || e?.message || 'Unknown error';
      const failed = toAdd[added];
      toast.error(`Failed to add ${failed?.name ?? 'model'}: ${detail}`);
      if (added > 0) queryClient.invalidateQueries({ queryKey: ['models'] });
      return;
    }
    queryClient.invalidateQueries({ queryKey: ['models'] });
    setIsDiscoverOpen(false);
    setDiscoveredModels([]);
    setSelectedDiscovered(new Set());
  };

  if (isLoading) {
    return <div className="text-slate-500 dark:text-gray-400">Loading models...</div>;
  }

  if (error) {
    return (
      <div className="p-6">
        <ErrorBanner
          message={`Failed to load models: ${error instanceof Error ? error.message : 'Unknown error'}`}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold">Model Presets</h1>
          <p className="text-slate-500 dark:text-gray-400 text-sm mt-1">
            {models.length} models configured across {availableProviders.length} providers
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="gap-2"
            onClick={handleValidateLocal}
            disabled={isValidatingLocal}
          >
            {isValidatingLocal ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Validate Local
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => setIsDiscoverOpen(true)}
          >
            Discover
          </Button>
          <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
              <Button className="bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-gray-900 font-semibold gap-2">
                <Plus className="w-4 h-4" />
                Add Model
              </Button>
            </DialogTrigger>
          <DialogContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
            <DialogHeader>
              <DialogTitle>Add Model Preset</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Qwen-80B Local"
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  required
                />
              </div>

              <div>
                <Label htmlFor="provider">Provider</Label>
                <Select value={formData.provider} onValueChange={handleProviderChange}>
                  <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                    {PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        <div className="flex items-center gap-2">
                          <ProviderLogo provider={p.value} size="sm" />
                          <span>{p.label}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="base_url">Base URL</Label>
                <Input
                  id="base_url"
                  value={formData.base_url}
                  onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  required
                />
              </div>

              <div>
                <Label htmlFor="model_id">Model ID</Label>
                <Input
                  id="model_id"
                  value={formData.model_id}
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                  placeholder="e.g., qwen/qwen3-80b"
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  required
                />
              </div>

              {formData.provider !== 'lmstudio' && (
                <div>
                  <Label htmlFor="api_key">API Key (optional - uses .env if empty)</Label>
                  <Input
                    id="api_key"
                    type="password"
                    value={formData.api_key}
                    onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                    placeholder="sk-..."
                    className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  />
                </div>
              )}

              {/* Vision Support */}
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="supportsVision"
                  checked={formData.supports_vision === true}
                  onCheckedChange={(checked: boolean) => {
                    setFormData({ ...formData, supports_vision: checked ? true : null });
                  }}
                />
                <Label htmlFor="supportsVision" className="cursor-pointer">
                  Supports Vision (images)
                </Label>
              </div>

              {/* Reasoning Configuration */}
              <div className="space-y-3 border-t border-stone-200 dark:border-gray-700 pt-4">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="isReasoning"
                    checked={formData.is_reasoning}
                    onCheckedChange={(checked: boolean) => {
                      setFormData({
                        ...formData,
                        is_reasoning: checked,
                        reasoning_level: checked ? 'high' : ''
                      });
                    }}
                  />
                  <Label htmlFor="isReasoning" className="cursor-pointer">
                    Enable Reasoning/Thinking Mode
                  </Label>
                </div>

                {formData.is_reasoning && (
                  <div className="ml-6">
                    <Label htmlFor="reasoningLevel">Reasoning Level</Label>
                    <Select
                      value={formData.reasoning_level}
                      onValueChange={(value) => setFormData({ ...formData, reasoning_level: value })}
                    >
                      <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 mt-1">
                        <SelectValue placeholder="Select level" />
                      </SelectTrigger>
                      <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High (Recommended)</SelectItem>
                        <SelectItem value="xhigh">Extra High (OpenAI only)</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground mt-1">
                      Higher levels = better reasoning, more tokens used
                    </p>
                  </div>
                )}
              </div>

              {/* Context Limit */}
              <div className="space-y-2">
                <Label htmlFor="contextLimit">Context Limit (tokens)</Label>
                <Input
                  id="contextLimit"
                  type="number"
                  placeholder="e.g., 128000"
                  value={formData.context_limit}
                  onChange={(e) => setFormData({ ...formData, context_limit: e.target.value })}
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                />
                <p className="text-xs text-muted-foreground">
                  Max input tokens for this model (optional)
                </p>
              </div>

              {/* Custom Temperature */}
              <div className="space-y-2">
                <Label htmlFor="customTemperature">Custom Temperature</Label>
                <Input
                  id="customTemperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  placeholder="Use mode default"
                  value={formData.custom_temperature}
                  onChange={(e) => setFormData({ ...formData, custom_temperature: e.target.value })}
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                />
                <p className="text-xs text-muted-foreground">{getCustomTemperatureHelpText()}</p>
              </div>

              {/* Max Concurrent Requests */}
              {(() => {
                const providerSetting = concurrencySettings.find(
                  (s) => s.provider === formData.provider && s.server_key === null
                );
                const effectiveValue = providerSetting?.max_concurrency;
                const isOverride = providerSetting?.is_override ?? false;
                const isLocal = formData.provider === 'lmstudio' || formData.provider === 'ollama';
                return (
                  <div className="space-y-2">
                    <Label htmlFor="maxConcurrency">Max Concurrent Requests</Label>
                    <Input
                      id="maxConcurrency"
                      type="number"
                      step="1"
                      min="1"
                      placeholder={effectiveValue != null ? String(effectiveValue) : 'Provider default'}
                      value={isOverride && effectiveValue != null ? effectiveValue : ''}
                      onChange={(e) => {
                        const val = e.target.value === '' ? null : Number(e.target.value);
                        concurrencyMutation.mutate({ provider: formData.provider, base_url: isLocal ? formData.base_url : null, max_concurrency: val });
                      }}
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                    />
                    <p className="text-xs text-muted-foreground">
                      {isLocal
                        ? `Applies to all models on this server. Clear to reset to default (${effectiveValue ?? '?'}).`
                        : `Applies to all ${formData.provider} models. Clear to reset to default (${effectiveValue ?? '?'}).`}
                    </p>
                  </div>
                );
              })()}

              {/* Pricing Override Section */}
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-300">
                  Pricing Override (optional)
                </summary>
                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="price_input">Input {formatPricingUnitLabel(formData.price_currency)}</Label>
                    <Input
                      id="price_input"
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.price_input}
                      onChange={(e) => setFormData({ ...formData, price_input: e.target.value })}
                      placeholder="Use default"
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                    />
                  </div>
                  <div>
                    <Label htmlFor="price_output">Output {formatPricingUnitLabel(formData.price_currency)}</Label>
                    <Input
                      id="price_output"
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.price_output}
                      onChange={(e) => setFormData({ ...formData, price_output: e.target.value })}
                      placeholder="Use default"
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                    />
                  </div>
                  <p className="col-span-2 text-xs text-slate-400 dark:text-gray-500">
                    Leave blank to use default pricing for {formData.provider}
                  </p>
                </div>
              </details>

              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Creating...' : 'Create'}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
        </div>
      </div>

      {(validationResults.length > 0 || validationError) && (
        <div className="space-y-3">
          {validationError && (
            <ErrorBanner
              message={`Local validation failed: ${validationError}`}
              onRetry={() => handleValidateLocal()}
            />
          )}

          {validationResults.length > 0 && (
            <Card className="bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50">
              <CardContent className="p-4 space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-800 dark:text-gray-200">Local Validation</h2>
                    <p className="text-sm text-slate-500 dark:text-gray-400">
                      Review drift, missing presets, and safe retarget suggestions before benchmarking.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {missingArchiveIds.length > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={() => archivePresets(missingArchiveIds)}
                      >
                        <Archive className="h-4 w-4" />
                        Archive Missing ({missingArchiveIds.length})
                      </Button>
                    )}
                    {selectedArchiveIds.length > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={() => archivePresets(selectedArchiveIds)}
                      >
                        <Archive className="h-4 w-4" />
                        Archive Selected ({selectedArchiveIds.length})
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-3">
                  {validationGroups.map((group) => {
                    const isOpen = activeValidationGroups.has(group.key);
                    const providerLabel = PROVIDERS.find((provider) => provider.value === group.provider)?.label || group.provider;
                    const hostLabel = getHostLabel(group.base_url) || group.base_url;
                    return (
                      <div key={group.key} className="rounded-lg border border-stone-200 dark:border-gray-700/50 bg-white/70 dark:bg-gray-900/20">
                        <button
                          type="button"
                          onClick={() => toggleValidationGroup(group.key)}
                          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              {isOpen ? <ChevronDown className="h-4 w-4 text-slate-500 dark:text-gray-400" /> : <ChevronRight className="h-4 w-4 text-slate-500 dark:text-gray-400" />}
                              <span className="font-medium text-slate-800 dark:text-gray-200">{providerLabel}</span>
                            </div>
                            <div className="mt-1 text-xs font-mono text-slate-500 dark:text-gray-400">{hostLabel}</div>
                          </div>
                          <span className="text-xs text-slate-500 dark:text-gray-400">{group.results.length} preset{group.results.length === 1 ? '' : 's'}</span>
                        </button>

                        {isOpen && (
                          <div className="space-y-3 border-t border-stone-200 dark:border-gray-700/50 px-4 py-3">
                            {group.results.map((result) => {
                              const model = modelsById.get(result.preset_id);
                              const isMissing = result.status === 'missing';
                              const hasRetarget = result.status === 'available_retarget_suggestion' && result.live_match?.model_id;
                              return (
                                <div key={`${group.key}-${result.preset_id}`} className="rounded-md border border-stone-200 dark:border-gray-700/50 bg-stone-50/80 dark:bg-gray-800/40 p-3">
                                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="min-w-0 space-y-1">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-medium text-slate-800 dark:text-gray-200">{model?.name || `Preset ${result.preset_id}`}</span>
                                        <ValidationStatusBadge status={result.status} />
                                      </div>
                                      <div className="text-xs font-mono text-slate-500 dark:text-gray-400">
                                        {model?.model_id || result.live_match?.model_id || result.preset_id}
                                      </div>
                                      <div className="text-sm text-slate-600 dark:text-gray-300">{result.message}</div>
                                      {result.live_match?.model_id && (
                                        <div className="text-xs text-slate-500 dark:text-gray-400">
                                          Live match: <span className="font-mono">{result.live_match.model_id}</span>
                                        </div>
                                      )}
                                      {result.metadata_drift.length > 0 && (
                                        <div className="text-xs text-slate-500 dark:text-gray-400">
                                          Drift fields: {result.metadata_drift.join(', ')}
                                        </div>
                                      )}
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      {isMissing && (
                                        <>
                                          <label className="flex items-center gap-2 text-xs text-slate-500 dark:text-gray-400">
                                            <Checkbox
                                              checked={selectedMissingPresetIds.has(result.preset_id)}
                                              onCheckedChange={(checked) => toggleMissingSelection(result.preset_id, checked === true)}
                                            />
                                            Select
                                          </label>
                                          <Button
                                            variant="outline"
                                            size="sm"
                                            className="gap-2"
                                            onClick={() => archivePresets([result.preset_id])}
                                          >
                                            <Archive className="h-4 w-4" />
                                            Archive
                                          </Button>
                                        </>
                                      )}
                                      {hasRetarget && (
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          onClick={() => openRetargetDialog(result)}
                                        >
                                          Preview Retarget
                                        </Button>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Filter and Sort Controls */}
      {models.length > 0 && (
        <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-stretch sm:items-center">
          <div className="flex-1 min-w-[200px] max-w-sm">
            <Input
              placeholder="Search by name or model ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50"
            />
          </div>
          <div className="w-full sm:w-[160px]">
            <Select value={providerFilter} onValueChange={setProviderFilter}>
              <SelectTrigger className="w-full sm:w-[160px] bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50" aria-label="Filter by provider">
                <SelectValue placeholder="All Providers" />
              </SelectTrigger>
              <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                <SelectItem value="all">All Providers</SelectItem>
                {availableProviders.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    <div className="flex items-center gap-2">
                      <ProviderLogo provider={p.value} size="sm" />
                      <span>{p.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-full sm:w-[160px]">
            <Select value={sortOption} onValueChange={setSortOption}>
              <SelectTrigger className="w-full sm:w-[160px] bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50" aria-label="Sort models by">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                {SORT_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* View Toggle */}
          <div className="flex rounded-lg border border-stone-200 dark:border-gray-700/50 overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 ${viewMode === 'grid' ? 'bg-stone-200 dark:bg-gray-700 text-gray-900 dark:text-white' : 'bg-stone-100 dark:bg-gray-800/50 text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}
              title="Grid view"
              aria-label="Grid view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 ${viewMode === 'list' ? 'bg-stone-200 dark:bg-gray-700 text-gray-900 dark:text-white' : 'bg-stone-100 dark:bg-gray-800/50 text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}
              title="List view"
              aria-label="List view"
            >
              <List className="w-4 h-4" />
            </button>
          </div>

          {(searchTerm || providerFilter !== 'all') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearchTerm('');
                setProviderFilter('all');
              }}
              className="text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            >
              Clear filters
            </Button>
          )}
          <span className="text-sm text-slate-500 dark:text-gray-400">
            {filteredModels.length} of {models.length}
          </span>
        </div>
      )}

      {models.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-full bg-stone-50 dark:bg-gray-800 flex items-center justify-center mb-4">
            <Plus className="w-8 h-8 text-slate-400 dark:text-gray-500" />
          </div>
          <h3 className="text-lg font-medium text-slate-700 dark:text-gray-300 mb-2">No models configured</h3>
          <p className="text-slate-500 dark:text-gray-400 mb-4">Add your first model to get started with benchmarking</p>
          <Button onClick={() => setIsOpen(true)} className="bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-gray-900">
            <Plus className="w-4 h-4 mr-2" />
            Add Model
          </Button>
        </div>
      ) : filteredModels.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-slate-500 dark:text-gray-400">No models match your filters</p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearchTerm(''); setProviderFilter('all'); }}
            className="mt-2 text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
          >
            Clear filters
          </Button>
        </div>
      ) : viewMode === 'grid' ? (
        /* Grid View */
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredModels.map((model: ModelPreset) => (
            <ModelCard
              key={model.id}
              model={model}
              testStatus={testStatus[model.id]}
              testResult={testResults[model.id] || undefined}
              onEdit={() => openEditDialog(model)}
              onTest={() => handleTest(model.id)}
              onDelete={() => handleDelete(model.id)}
            />
          ))}
        </div>
      ) : (
        /* List View */
        <Card className="bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50 overflow-hidden">
          <div className="divide-y divide-stone-200 dark:divide-gray-700/50">
            {filteredModels.map((model: ModelPreset) => (
              <ModelListItem
                key={model.id}
                model={model}
                testStatus={testStatus[model.id]}
                testResult={testResults[model.id] || undefined}
                onEdit={() => openEditDialog(model)}
                onTest={() => handleTest(model.id)}
                onDelete={() => handleDelete(model.id)}
              />
            ))}
          </div>
        </Card>
      )}

      {/* Discover Models Dialog — scan results intentionally persist across open/close */}
      <Dialog open={isDiscoverOpen} onOpenChange={(open) => {
        setIsDiscoverOpen(open);
        if (!open) {
          setDiscoverSearch('');
          setDiscoverSort('default');
          setDiscoverCapability('all');
          setDiscoverShowSelectedOnly(false);
        }
      }}>
        <DialogContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 w-[calc(100vw-1.5rem)] sm:w-[calc(100vw-3rem)] max-w-4xl h-[75vh] flex flex-col overflow-hidden overflow-x-hidden">
          <DialogHeader className="shrink-0">
            <DialogTitle>Discover Models</DialogTitle>
          </DialogHeader>

          {/* Controls — compact */}
          <div className="space-y-3 shrink-0">
            {/* Row 1: Provider + URL/Scan */}
            <div className="flex flex-wrap gap-3 items-end">
              <div className="w-full sm:w-48 sm:shrink-0">
                <Label className="text-xs mb-1 block">Provider</Label>
                <Select value={discoverProvider} onValueChange={(v) => {
                  setDiscoverProvider(v);
                  setDiscoveredModels([]);
                  setSelectedDiscovered(new Set());
                  setDiscoverSearch('');
                  setDiscoverSort('default');
                  setDiscoverCapability('all');
                  setDiscoverShowSelectedOnly(false);
                  if (v === 'lmstudio') setDiscoverUrl('http://localhost:1234');
                  else if (v === 'ollama') setDiscoverUrl('http://localhost:11434');
                }}>
                  <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                    {PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        <div className="flex items-center gap-2">
                          <ProviderLogo provider={p.value} size="sm" />
                          <span>{p.label}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {(discoverProvider === 'lmstudio' || discoverProvider === 'ollama') && (
                <div className="flex-1 min-w-[220px]">
                  <Label className="text-xs mb-1 block">Server URL</Label>
                  <Input
                    value={discoverUrl}
                    onChange={(e) => setDiscoverUrl(e.target.value)}
                    className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                    placeholder={discoverProvider === 'ollama' ? "http://localhost:11434" : "http://localhost:1234"}
                  />
                </div>
              )}
              <Button onClick={handleScan} disabled={isScanning} className="w-full sm:w-auto shrink-0">
                {isScanning ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Scanning...</>
                ) : 'Scan'}
              </Button>
            </div>

            {/* Row 2: API key for cloud providers */}
            {discoverProvider !== 'lmstudio' && discoverProvider !== 'ollama' && (
              <div>
                <Label className="text-xs mb-1 block">API Key (optional - uses .env if empty)</Label>
                <Input
                  type="password"
                  value={discoverKey}
                  onChange={(e) => setDiscoverKey(e.target.value)}
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  placeholder="Uses .env key by default"
                />
              </div>
            )}
          </div>

          {/* Results section — grows to fill remaining space */}
          {discoveredModels.length > 0 && (
            <div className="flex flex-col min-h-0 flex-1 mt-2">
              {/* Search + sort toolbar */}
              <div className="flex flex-wrap items-center gap-3 mb-2 shrink-0">
                <div className="relative flex-1 min-w-[220px]">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 dark:text-gray-500" />
                  <Input
                    value={discoverSearch}
                    onChange={(e) => setDiscoverSearch(e.target.value)}
                    className="pl-8 bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 h-9"
                    placeholder="Search models, model IDs, vision, reasoning..."
                    aria-label="Search discovered models"
                  />
                </div>
                <Select value={discoverSort} onValueChange={(v) => setDiscoverSort(v as DiscoverSort)}>
                  <SelectTrigger className="w-full sm:w-40 bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 h-9" aria-label="Sort discovered models">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                    <SelectItem value="default">Default order</SelectItem>
                    <SelectItem value="az">Name A → Z</SelectItem>
                    <SelectItem value="za">Name Z → A</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Filter chips */}
              <div className="flex flex-wrap items-center gap-2 mb-2 shrink-0">
                <Button
                  type="button"
                  size="sm"
                  variant={discoverCapability === 'all' ? 'secondary' : 'outline'}
                  className="h-7 text-xs"
                  onClick={() => setDiscoverCapability('all')}
                >
                  All
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={discoverCapability === 'vision' ? 'secondary' : 'outline'}
                  className="h-7 text-xs gap-1"
                  onClick={() => setDiscoverCapability('vision')}
                >
                  <Eye className="h-3 w-3" />
                  Vision
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={discoverCapability === 'reasoning' ? 'secondary' : 'outline'}
                  className="h-7 text-xs gap-1"
                  onClick={() => setDiscoverCapability('reasoning')}
                >
                  <Brain className="h-3 w-3" />
                  Reasoning
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={discoverShowSelectedOnly ? 'secondary' : 'outline'}
                  className="h-7 text-xs"
                  onClick={() => setDiscoverShowSelectedOnly((prev) => !prev)}
                >
                  Selected only ({selectedDiscovered.size})
                </Button>
                {hasDiscoverFilters && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => {
                      setDiscoverSearch('');
                      setDiscoverCapability('all');
                      setDiscoverShowSelectedOnly(false);
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </div>

              {/* Count + select/clear */}
              <div className="flex items-center justify-between mb-1 shrink-0">
                <Label className="text-xs text-slate-500 dark:text-gray-400">
                  {filteredDiscoveredModels.length} of {discoveredModels.length} models
                </Label>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setSelectedDiscovered(
                      new Set(filteredDiscoveredModels.map(m => m._origIndex))
                    )}
                  >
                    {hasDiscoverFilters ? 'Select Visible' : 'Select All'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setSelectedDiscovered(new Set())}
                  >
                    Clear
                  </Button>
                </div>
              </div>

              {/* Scrollable model list */}
              <div className="flex-1 overflow-y-auto overflow-x-hidden border border-stone-200 dark:border-gray-700 rounded p-1 space-y-0.5">
                {filteredDiscoveredModels.map((m) => (
                  (() => {
                    const reasoningBadge = getReasoningBadgeLabel(m);
                    return (
                      <label
                        key={`${m.model_id}-${m.is_reasoning}-${m._origIndex}`}
                        className={`flex min-w-0 items-center gap-3 px-2 py-1.5 rounded cursor-pointer hover:bg-stone-100 dark:hover:bg-gray-700/50 ${
                          selectedDiscovered.has(m._origIndex) ? 'bg-stone-100 dark:bg-gray-700/30' : ''
                        }`}
                      >
                        <Checkbox
                          checked={selectedDiscovered.has(m._origIndex)}
                          onCheckedChange={(checked: boolean) => {
                            setSelectedDiscovered(prev => {
                              const next = new Set(prev);
                              if (checked) next.add(m._origIndex);
                              else next.delete(m._origIndex);
                              return next;
                            });
                          }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-sm text-slate-800 dark:text-gray-200 min-w-0 flex-1 truncate">{m.name || m.model_id || m.model}</span>
                            {reasoningBadge && (
                              <Badge variant="secondary" className="text-[10px] bg-purple-500/20 text-purple-300 border-purple-500/30 shrink-0">
                                <Brain className="h-3 w-3 mr-0.5" />
                                {reasoningBadge}
                              </Badge>
                            )}
                            {m.supports_vision && (
                              <Badge variant="secondary" className="text-[10px] bg-blue-500/20 text-blue-300 border-blue-500/30 shrink-0">
                                <Eye className="h-3 w-3" />
                              </Badge>
                            )}
                          </div>
                          <span className="text-xs text-slate-500 dark:text-gray-400 font-mono truncate block">{m.model_id}</span>
                          <CompactModelMetadataRow model={m} className="mt-1" />
                        </div>
                      </label>
                    );
                  })()
                ))}
                {filteredDiscoveredModels.length === 0 && (discoverSearch || discoverCapability !== 'all' || discoverShowSelectedOnly) && (
                  <div className="text-center text-sm text-slate-400 dark:text-gray-500 py-8">
                    No models match current filters
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Footer — add button */}
          {selectedDiscovered.size > 0 && (
            <div className="flex justify-end pt-2 shrink-0 border-t border-stone-200 dark:border-gray-700">
              <Button onClick={handleAddDiscovered}>
                Add {selectedDiscovered.size} Model{selectedDiscovered.size > 1 ? 's' : ''}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog */}
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <DialogHeader>
            <DialogTitle>Edit Model Preset</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div>
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={editFormData.name}
                onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                required
              />
            </div>

            <div>
              <Label htmlFor="edit-provider">Provider</Label>
              <Select value={editFormData.provider} onValueChange={handleEditProviderChange}>
                <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      <div className="flex items-center gap-2">
                        <ProviderLogo provider={p.value} size="sm" />
                        <span>{p.label}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="edit-base_url">Base URL</Label>
              <Input
                id="edit-base_url"
                value={editFormData.base_url}
                onChange={(e) => setEditFormData({ ...editFormData, base_url: e.target.value })}
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                required
              />
            </div>

            <div>
              <Label htmlFor="edit-model_id">Model ID</Label>
              <Input
                id="edit-model_id"
                value={editFormData.model_id}
                onChange={(e) => setEditFormData({ ...editFormData, model_id: e.target.value })}
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                required
              />
            </div>

            {editFormData.provider !== 'lmstudio' && (
              <div>
                <Label htmlFor="edit-api_key">API Key (leave empty to keep existing)</Label>
                <Input
                  id="edit-api_key"
                  type="password"
                  value={editFormData.api_key}
                  onChange={(e) => setEditFormData({ ...editFormData, api_key: e.target.value })}
                  placeholder="Enter new key or leave empty"
                  className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                />
              </div>
            )}

            {/* Vision Support */}
            <div className="flex items-center space-x-2">
              <Checkbox
                id="editSupportsVision"
                checked={editFormData.supports_vision === true}
                onCheckedChange={(checked: boolean) => {
                  setEditFormData({ ...editFormData, supports_vision: checked ? true : null });
                }}
              />
              <Label htmlFor="editSupportsVision" className="cursor-pointer">
                Supports Vision (images)
              </Label>
            </div>

            {/* Reasoning Configuration */}
            <div className="space-y-3 border-t border-stone-200 dark:border-gray-700 pt-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="editIsReasoning"
                  checked={editFormData.is_reasoning}
                  onCheckedChange={(checked: boolean) => {
                    setEditFormData({
                      ...editFormData,
                      is_reasoning: checked,
                      reasoning_level: checked ? 'high' : ''
                    });
                  }}
                />
                <Label htmlFor="editIsReasoning" className="cursor-pointer">
                  Enable Reasoning/Thinking Mode
                </Label>
              </div>

              {editFormData.is_reasoning && (
                <div className="ml-6">
                  <Label htmlFor="editReasoningLevel">Reasoning Level</Label>
                  <Select
                    value={editFormData.reasoning_level}
                    onValueChange={(value) => setEditFormData({ ...editFormData, reasoning_level: value })}
                  >
                    <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 mt-1">
                      <SelectValue placeholder="Select level" />
                    </SelectTrigger>
                    <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High (Recommended)</SelectItem>
                      <SelectItem value="xhigh">Extra High (OpenAI only)</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">
                    Higher levels = better reasoning, more tokens used
                  </p>
                </div>
              )}
            </div>

            {/* Context Limit */}
            <div className="space-y-2">
              <Label htmlFor="editContextLimit">Context Limit (tokens)</Label>
              <Input
                id="editContextLimit"
                type="number"
                placeholder="e.g., 128000"
                value={editFormData.context_limit}
                onChange={(e) => setEditFormData({ ...editFormData, context_limit: e.target.value })}
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
              />
              <p className="text-xs text-muted-foreground">
                Max input tokens for this model (optional)
              </p>
            </div>

            {/* Custom Temperature */}
            <div className="space-y-2">
              <Label htmlFor="editCustomTemperature">Custom Temperature</Label>
              <Input
                id="editCustomTemperature"
                type="number"
                step="0.1"
                min="0"
                max="2"
                placeholder="Use mode default"
                value={editFormData.custom_temperature}
                onChange={(e) => setEditFormData({ ...editFormData, custom_temperature: e.target.value })}
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
              />
              <p className="text-xs text-muted-foreground">{getCustomTemperatureHelpText()}</p>
            </div>

            {/* Max Concurrent Requests */}
            {(() => {
              const providerSetting = concurrencySettings.find(
                (s) => s.provider === editFormData.provider && s.server_key === null
              );
              const effectiveValue = providerSetting?.max_concurrency;
              const isOverride = providerSetting?.is_override ?? false;
              const isLocal = editFormData.provider === 'lmstudio' || editFormData.provider === 'ollama';
              return (
                <div className="space-y-2">
                  <Label htmlFor="editMaxConcurrency">Max Concurrent Requests</Label>
                  <Input
                    id="editMaxConcurrency"
                    type="number"
                    step="1"
                    min="1"
                    placeholder={effectiveValue != null ? String(effectiveValue) : 'Provider default'}
                    value={isOverride && effectiveValue != null ? effectiveValue : ''}
                    onChange={(e) => {
                      const val = e.target.value === '' ? null : Number(e.target.value);
                      concurrencyMutation.mutate({ provider: editFormData.provider, base_url: isLocal ? editFormData.base_url : null, max_concurrency: val });
                    }}
                    className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  />
                  <p className="text-xs text-muted-foreground">
                    {isLocal
                      ? `Applies to all models on this server. Clear to reset to default (${effectiveValue ?? '?'}).`
                      : `Applies to all ${editFormData.provider} models. Clear to reset to default (${effectiveValue ?? '?'}).`}
                  </p>
                </div>
              );
            })()}

            {/* Quant Metadata */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Quantization</label>
                <input
                  type="text"
                  value={editFormData.quantization || ''}
                  onChange={(e) => setEditFormData({...editFormData, quantization: e.target.value || null})}
                  placeholder="e.g. Q4_K_M, 4bit"
                  className="w-full px-3 py-2 text-sm border rounded dark:bg-gray-800 dark:border-gray-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Format</label>
                <input
                  type="text"
                  value={editFormData.model_format || ''}
                  onChange={(e) => setEditFormData({...editFormData, model_format: e.target.value || null})}
                  placeholder="e.g. GGUF, MLX"
                  className="w-full px-3 py-2 text-sm border rounded dark:bg-gray-800 dark:border-gray-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Source</label>
                <input
                  type="text"
                  value={editFormData.model_source || ''}
                  onChange={(e) => setEditFormData({...editFormData, model_source: e.target.value || null})}
                  placeholder="e.g. mlx-community"
                  className="w-full px-3 py-2 text-sm border rounded dark:bg-gray-800 dark:border-gray-600"
                />
              </div>
            </div>

            {/* Pricing Override Section */}
            <details className="mt-4" open={editFormData.price_input !== '' || editFormData.price_output !== ''}>
              <summary className="cursor-pointer text-sm text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-300">
                Pricing Override (optional)
              </summary>
              <div className="mt-3 grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-price_input">Input {formatPricingUnitLabel(editFormData.price_currency)}</Label>
                  <Input
                    id="edit-price_input"
                    type="number"
                    step="0.01"
                    min="0"
                    value={editFormData.price_input}
                    onChange={(e) => setEditFormData({ ...editFormData, price_input: e.target.value })}
                    placeholder="Use default"
                    className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  />
                </div>
                <div>
                  <Label htmlFor="edit-price_output">Output {formatPricingUnitLabel(editFormData.price_currency)}</Label>
                  <Input
                    id="edit-price_output"
                    type="number"
                    step="0.01"
                    min="0"
                    value={editFormData.price_output}
                    onChange={(e) => setEditFormData({ ...editFormData, price_output: e.target.value })}
                    placeholder="Use default"
                    className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  />
                </div>
                <p className="col-span-2 text-xs text-slate-400 dark:text-gray-500">
                  Leave blank to use default pricing for {editFormData.provider}
                </p>
              </div>
            </details>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={closeEditDialog}>
                Cancel
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm({ open, id: null })}
        title="Archive Model Preset"
        description="Archive this model preset to hide it from future runs. You can still retrieve archived presets later."
        confirmLabel="Archive"
        variant="destructive"
        onConfirm={() => {
          if (deleteConfirm.id !== null) {
            deleteMutation.mutate(deleteConfirm.id);
          }
        }}
      />

      <Dialog open={isRetargetDialogOpen} onOpenChange={setIsRetargetDialogOpen}>
        <DialogContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <DialogHeader>
            <DialogTitle>Confirm Retarget</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-gray-300">
              Review each preset mapping before applying the retarget update.
            </p>
            <div className="space-y-2">
              {retargetPreview.map((item) => (
                <div key={item.presetId} className="rounded-md border border-stone-200 dark:border-gray-700/50 bg-white/70 dark:bg-gray-900/20 p-3 text-sm">
                  <div className="font-medium text-slate-800 dark:text-gray-200">{item.from}</div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-gray-400">
                    <span className="font-mono">{item.from}</span> → <span className="font-mono">{item.to}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setIsRetargetDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => handleConfirmRetarget()}
                disabled={retargetMutation.isPending}
              >
                {retargetMutation.isPending ? 'Applying...' : 'Apply Retarget'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Model Card Component for Grid View
function ModelCard({
  model,
  testStatus,
  testResult,
  onEdit,
  onTest,
  onDelete
}: {
  model: ModelPreset;
  testStatus?: string;
  testResult?: ModelTestResult | null;
  onEdit: () => void;
  onTest: () => void;
  onDelete: () => void;
}) {
  const getProviderColor = (provider: string) => {
    const colors: Record<string, string> = {
      anthropic: 'border-orange-500/30 bg-orange-500/5',
      openai: 'border-green-500/30 bg-green-500/5',
      google: 'border-blue-500/30 bg-blue-500/5',
      mistral: 'border-purple-500/30 bg-purple-500/5',
      deepseek: 'border-cyan-500/30 bg-cyan-500/5',
      grok: 'border-red-500/30 bg-red-500/5',
      glm: 'border-yellow-500/30 bg-yellow-500/5',
      kimi: 'border-pink-500/30 bg-pink-500/5',
      lmstudio: 'border-gray-500/30 bg-gray-500/5',
    };
    return colors[provider] || 'border-stone-200 dark:border-gray-700/50 bg-stone-100 dark:bg-gray-800/50';
  };
  const reasoningBadge = getReasoningBadgeLabel(model);

  return (
    <Card className={`group relative transition-all duration-200 hover:shadow-lg hover:scale-[1.02] border ${getProviderColor(model.provider)}`}>
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <ProviderLogo provider={model.provider} size="md" />
          <div className="min-w-0 flex-1">
            <h3 className="font-medium text-slate-800 dark:text-gray-200 truncate">{model.name}</h3>
            {(model.quantization || model.model_format || model.model_source) && (
              <div className="flex flex-wrap gap-1 mt-1">
                {model.model_format && (
                  <span className="px-1.5 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                    {model.model_format}
                  </span>
                )}
                {model.quantization && (
                  <span className="px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded">
                    {model.quantization}
                  </span>
                )}
                {model.model_source && (
                  <span className="px-1.5 py-0.5 text-xs bg-slate-100 dark:bg-slate-700/30 text-slate-600 dark:text-slate-300 rounded truncate max-w-[150px]">
                    {model.model_source}
                  </span>
                )}
              </div>
            )}
            <p className="text-xs text-slate-500 dark:text-gray-400">
              {model.provider}
              {getHostLabel(model.base_url) && (
                <span className="text-slate-500 dark:text-gray-400"> · {getHostLabel(model.base_url)}</span>
              )}
            </p>
          </div>
        </div>
        {/* Badges */}
        {(reasoningBadge || model.supports_vision || (model.price_input != null && model.price_output != null)) && (
          <div className="flex flex-wrap gap-1 mb-3 ml-10">
            {reasoningBadge && (
              <Badge variant="secondary" className="text-xs bg-purple-500/20 text-purple-300 border-purple-500/30">
                <Brain className="h-3 w-3 mr-1" />
                {reasoningBadge}
              </Badge>
            )}
            {model.supports_vision && (
              <Badge variant="secondary" className="text-xs bg-blue-500/20 text-blue-300 border-blue-500/30">
                <Eye className="h-3 w-3" />
              </Badge>
            )}
            <PricingBadgesRow model={model} />
          </div>
        )}
        {!(reasoningBadge || model.supports_vision || (model.price_input != null && model.price_output != null)) && (
          <div className="mb-3" />
        )}

        {/* Model ID */}
        <div className="mb-3">
          <p className="text-xs text-slate-500 dark:text-gray-400 mb-1">Model ID</p>
          <p className="text-sm font-mono text-slate-500 dark:text-gray-400 truncate" title={model.model_id}>
            {model.model_id}
          </p>
          <CompactModelMetadataRow model={model} className="mt-2" />
        </div>

        {/* Status indicators */}
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-gray-400 mb-4">
          {model.has_api_key && (
            <span className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
              API Key Set
            </span>
          )}
          {model.context_limit && (
            <span>{(model.context_limit / 1000).toFixed(0)}K ctx</span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={onEdit}
            className="flex-1 text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-stone-100 dark:hover:bg-gray-700/50"
          >
            <Pencil className="w-3.5 h-3.5 mr-1.5" />
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onTest}
            disabled={testStatus === 'testing'}
            className="flex-1 text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-stone-100 dark:hover:bg-gray-700/50"
          >
            {testStatus === 'testing' ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : testStatus === 'success' ? (
              <Check className="w-3.5 h-3.5 mr-1.5 text-green-600 dark:text-green-400" />
            ) : testStatus === 'failed' ? (
              <X className="w-3.5 h-3.5 mr-1.5 text-red-600 dark:text-red-400" />
            ) : (
              <Play className="w-3.5 h-3.5 mr-1.5" />
            )}
            Test
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDelete}
            className="text-slate-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-500/10"
            aria-label="Archive model"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
        {testResult && <ModelTestResultPanel result={testResult} />}
      </CardContent>
    </Card>
  );
}

// Model List Item Component for List View
function ModelListItem({
  model,
  testStatus,
  testResult,
  onEdit,
  onTest,
  onDelete
}: {
  model: ModelPreset;
  testStatus?: string;
  testResult?: ModelTestResult | null;
  onEdit: () => void;
  onTest: () => void;
  onDelete: () => void;
}) {
  const reasoningBadge = getReasoningBadgeLabel(model);

  return (
    <div className="flex items-center gap-4 p-4 hover:bg-stone-100 dark:hover:bg-gray-700/30 transition-colors">
      {/* Provider Logo */}
      <ProviderLogo provider={model.provider} size="md" />

      {/* Main Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-slate-800 dark:text-gray-200 truncate">{model.name}</h3>
          {reasoningBadge && (
            <Badge variant="secondary" className="text-xs bg-purple-500/20 text-purple-300 border-purple-500/30 shrink-0">
              <Brain className="h-3 w-3 mr-1" />
              {reasoningBadge}
            </Badge>
          )}
          {model.supports_vision && (
            <Badge variant="secondary" className="text-xs bg-blue-500/20 text-blue-300 border-blue-500/30 shrink-0">
              <Eye className="h-3 w-3" />
            </Badge>
          )}
          {model.model_format && (
            <span className="px-1.5 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded shrink-0">
              {model.model_format}
            </span>
          )}
          {model.quantization && (
            <span className="px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded shrink-0">
              {model.quantization}
            </span>
          )}
          {model.model_source && (
            <span className="px-1.5 py-0.5 text-xs bg-slate-100 dark:bg-slate-700/30 text-slate-600 dark:text-slate-300 rounded truncate max-w-[150px] shrink-0">
              {model.model_source}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-500 dark:text-gray-400 font-mono truncate">{model.model_id}</p>
        <CompactModelMetadataRow model={model} className="mt-1" />
        <PricingBadgesRow model={model} className="mt-1" badgeClassName="text-[11px]" />
      </div>

      {/* Provider */}
      <div className="hidden sm:block text-sm text-slate-500 dark:text-gray-400 w-32">
        {model.provider}
        {getHostLabel(model.base_url) && (
          <div className="text-xs text-slate-400 dark:text-gray-600">{getHostLabel(model.base_url)}</div>
        )}
      </div>

      {/* API Key Status */}
      <div className="hidden md:flex items-center gap-1.5 w-20">
        {model.has_api_key ? (
          <>
            <div className="w-2 h-2 rounded-full bg-green-400" />
            <span className="text-xs text-slate-500 dark:text-gray-400">Set</span>
          </>
        ) : (
          <span className="text-xs text-slate-500 dark:text-gray-400">—</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant="ghost"
          onClick={onEdit}
          className="text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          aria-label="Edit model"
        >
          <Pencil className="w-4 h-4" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onTest}
          disabled={testStatus === 'testing'}
          className="text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          aria-label="Test model connection"
        >
          {testStatus === 'testing' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : testStatus === 'success' ? (
            <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
          ) : testStatus === 'failed' ? (
            <X className="w-4 h-4 text-red-600 dark:text-red-400" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onDelete}
          className="text-slate-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400"
          aria-label="Archive model"
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
      {testResult && (
        <div className="basis-full pl-12">
          <ModelTestResultPanel result={testResult} />
        </div>
      )}
    </div>
  );
}
