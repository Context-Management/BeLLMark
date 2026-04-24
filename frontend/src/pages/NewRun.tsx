import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { modelsApi, benchmarksApi, questionsApi, criteriaApi, suitesApi, attachmentsApi } from '@/lib/api';
import {
  filterAndSortNewRunModels,
  type NewRunSelectionFilter,
  type NewRunVisionFilter,
  type NewRunReasoningFilter,
  type NewRunSortBy,
} from '@/lib/newRunModelFilters';
import { getHostLabel } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AttachmentButton, type Attachment } from '@/components/ui/attachment-uploader';
import { AttachmentList } from '@/components/ui/attachment-list';
import { ProviderLogo } from '@/components/ui/provider-logo';
import {
  getTemperatureModeDescription,
  getTemperatureModeLabel,
} from '@/lib/temperatureCopy';
import { Brain, Search, Filter, ArrowUpDown, Eye } from 'lucide-react';
import type { QuestionWithAttachments as Question, Criterion } from '@/types/api';

// Family-level judge/model overlap detection (mirrors backend logic, C18)
const MODEL_FAMILIES: Record<string, string[]> = {
  // Use broad prefixes so the check survives model-generation bumps without
  // code changes (e.g. GPT-5.x, Claude Opus 4.x, Claude Sonnet 4.x).
  openai: ['gpt-', 'gpt4', 'o1', 'o3', 'o4'],
  anthropic: ['claude-'],
  google: ['gemini', 'gemma', 'palm'],
  mistral: ['mistral', 'mixtral', 'codestral', 'pixtral'],
  deepseek: ['deepseek'],
  meta: ['llama'],
  grok: ['grok'],
  qwen: ['qwen'],
};

function getModelFamily(modelId: string): string | null {
  const lower = modelId.toLowerCase();
  for (const [family, prefixes] of Object.entries(MODEL_FAMILIES)) {
    if (prefixes.some((p) => lower.startsWith(p))) return family;
  }
  return null;
}

interface FamilyOverlapWarning {
  judge: string;
  model: string;
  family: string;
  message: string;
}

const DEFAULT_CRITERIA: Criterion[] = [
  { name: 'Accuracy', description: 'Factual correctness and relevance', weight: 1 },
  { name: 'Creativity', description: 'Originality and creative expression', weight: 1 },
  { name: 'Clarity', description: 'Clear and well-structured writing', weight: 1 },
];

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

  if (model.parameter_count) metadata.push({ key: 'parameter_count', label: model.parameter_count, title: 'Parameter count' });
  if (model.quantization_bits != null) metadata.push({ key: 'quantization_bits', label: formatQuantizationBits(model.quantization_bits), title: 'Quantization bits per weight' });
  if (model.model_architecture) metadata.push({ key: 'model_architecture', label: model.model_architecture, title: 'Model architecture' });
  if (model.selected_variant && model.selected_variant !== model.model_id) metadata.push({ key: 'selected_variant', label: model.selected_variant, title: 'Selected variant' });
  if (model.context_limit) metadata.push({ key: 'context_limit', label: `${(model.context_limit / 1000).toFixed(0)}K ctx`, title: 'Context window' });

  return metadata;
}

export function NewRun() {
  const navigate = useNavigate();
  const location = useLocation();
  const cloneData = (location.state as { cloneFrom?: {
    name: string;
    questions: { system_prompt: string; user_prompt: string; expected_answer?: string | null }[];
    criteria: { name: string; description: string; weight: number }[];
    judgeMode: string;
    modelIds?: number[];
    judgeIds?: number[];
  } })?.cloneFrom;
  const rejudgeData = (location.state as { rejudgeFrom?: {
    parentRunId: number;
    name: string;
    criteria: { name: string; description: string; weight: number }[];
    judgeMode: string;
    modelIds?: number[];
    judgeIds?: number[];
  } })?.rejudgeFrom;
  const suiteId = (location.state as { suiteId?: number })?.suiteId;

  const [step, setStep] = useState(1);

  // Form state
  const [name, setName] = useState('');
  const [selectedModels, setSelectedModels] = useState<number[]>([]);
  const [selectedJudges, setSelectedJudges] = useState<number[]>([]);
  const [judgeMode, setJudgeMode] = useState<'comparison' | 'separate'>('comparison');
  const [questions, setQuestions] = useState<Question[]>([{ system_prompt: '', user_prompt: '', attachment_ids: [] }]);
  const [criteria, setCriteria] = useState<Criterion[]>(DEFAULT_CRITERIA);
  const [temperature, setTemperature] = useState(0.7);
  const [temperatureMode, setTemperatureMode] = useState<'normalized' | 'provider_default' | 'custom'>('normalized');
  const [sequentialMode, setSequentialMode] = useState(false);
  const [questionAttachments, setQuestionAttachments] = useState<Record<number, Attachment[]>>({});
  const [globalAttachments, setGlobalAttachments] = useState<Attachment[]>([]);

  // AI generation state
  const [aiTopic, setAiTopic] = useState('');
  const [aiCount, setAiCount] = useState(5);
  const [aiModelIds, setAiModelIds] = useState<number[]>([]);
  const [aiContextAttachment, setAiContextAttachment] = useState<Attachment | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingCriteria, setIsGeneratingCriteria] = useState(false);
  const [criteriaTopic, setCriteriaTopic] = useState('');
  const [criteriaCount, setCriteriaCount] = useState(4);
  const [activeTab, setActiveTab] = useState('manual');
  const [sourceSuiteId, setSourceSuiteId] = useState<number | null>(null);
  const [suiteCriteriaLoaded, setSuiteCriteriaLoaded] = useState<string | null>(null);

  // Model filtering/sorting state
  const [modelSearch, setModelSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [reasoningFilter, setReasoningFilter] = useState<NewRunReasoningFilter>('all');
  const [selectionFilter, setSelectionFilter] = useState<NewRunSelectionFilter>('all');
  const [visionFilter, setVisionFilter] = useState<NewRunVisionFilter>('all');
  const [sortBy, setSortBy] = useState<NewRunSortBy>('provider');

  // Judge filtering state
  const [judgeSearch, setJudgeSearch] = useState('');
  const [judgeProviderFilter, setJudgeProviderFilter] = useState<string>('all');
  const [judgeReasoningFilter, setJudgeReasoningFilter] = useState<'all' | 'reasoning' | 'standard'>('all');

  const { data: models = [] } = useQuery({
    queryKey: ['models'],
    queryFn: async () => (await modelsApi.list()).data,
  });

  const { data: suites = [] } = useQuery({
    queryKey: ['suites'],
    queryFn: async () => (await suitesApi.list()).data,
  });

  // Fetch completed runs for judge usage frequency
  const { data: runs = [] } = useQuery({
    queryKey: ['benchmarks'],
    queryFn: async () => (await benchmarksApi.list()).data,
  });

  // Get unique providers for filter dropdown
  const providers = useMemo(() => {
    const providerSet = new Set(models.map((m) => m.provider));
    return Array.from(providerSet).sort();
  }, [models]);

  // Model usage frequency: count how often each model has been used in benchmark runs
  const modelUsageCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const run of runs) {
      if (run.model_ids) {
        for (const id of run.model_ids) {
          counts.set(id, (counts.get(id) || 0) + 1);
        }
      }
    }
    return counts;
  }, [runs]);

  // Filter and sort models
  const filteredModels = useMemo(() => {
    return filterAndSortNewRunModels(models, {
      searchTerm: modelSearch,
      providerFilter,
      reasoningFilter,
      selectionFilter,
      visionFilter,
      sortBy,
      selectedModelIds: new Set(selectedModels),
      usageCounts: modelUsageCounts,
    });
  }, [models, modelSearch, providerFilter, reasoningFilter, selectionFilter, visionFilter, sortBy, selectedModels, modelUsageCounts]);

  // Judge usage frequency: count how often each model has been used as a judge
  const judgeUsageCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const run of runs) {
      if (run.judge_ids) {
        for (const id of run.judge_ids) {
          counts.set(id, (counts.get(id) || 0) + 1);
        }
      }
    }
    return counts;
  }, [runs]);

  // Filter and sort judges: frequency-first by default, with provider + reasoning filters
  const filteredJudges = useMemo(() => {
    let filtered = [...models];

    // Text search
    if (judgeSearch) {
      const q = judgeSearch.toLowerCase();
      filtered = filtered.filter(
        (m) => m.name.toLowerCase().includes(q) || m.model_id.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q)
      );
    }

    // Provider filter
    if (judgeProviderFilter !== 'all') {
      filtered = filtered.filter((m) => m.provider === judgeProviderFilter);
    }

    // Reasoning filter
    if (judgeReasoningFilter === 'reasoning') {
      filtered = filtered.filter((m) => m.is_reasoning);
    } else if (judgeReasoningFilter === 'standard') {
      filtered = filtered.filter((m) => !m.is_reasoning);
    }

    // Sort: usage frequency (desc), then by provider, then name
    // Note: no "selected first" to avoid items jumping when toggling checkboxes
    filtered.sort((a, b) => {
      const aCount = judgeUsageCounts.get(a.id) || 0;
      const bCount = judgeUsageCounts.get(b.id) || 0;
      if (aCount !== bCount) return bCount - aCount;
      const provCmp = a.provider.localeCompare(b.provider);
      if (provCmp !== 0) return provCmp;
      return a.name.localeCompare(b.name);
    });

    return filtered;
  }, [models, judgeSearch, judgeProviderFilter, judgeReasoningFilter, judgeUsageCounts]);

  // Detect family-level judge/model overlap in real time (C18 — preference leakage)
  const familyOverlapWarnings = useMemo<FamilyOverlapWarning[]>(() => {
    const evalModels = models.filter((m) => selectedModels.includes(m.id));
    const judgeModels = models.filter((m) => selectedJudges.includes(m.id));
    const warnings: FamilyOverlapWarning[] = [];
    for (const judge of judgeModels) {
      const judgeFamily = getModelFamily(judge.model_id);
      if (!judgeFamily) continue;
      for (const evalModel of evalModels) {
        if (getModelFamily(evalModel.model_id) === judgeFamily) {
          warnings.push({
            judge: judge.name,
            model: evalModel.name,
            family: judgeFamily,
            message: `${judge.name} and ${evalModel.name} are from the same model family (${judgeFamily}). Research shows this can inflate scores by up to 23.6% on average (lin2025).`,
          });
        }
      }
    }
    return warnings;
  }, [models, selectedModels, selectedJudges]);

  useEffect(() => {
    if (cloneData) {
      setName(cloneData.name);
      setQuestions(cloneData.questions.map(q => ({
        ...q,
        attachment_ids: []
      })));
      setCriteria(cloneData.criteria);
      if (cloneData.judgeMode === 'comparison' || cloneData.judgeMode === 'separate') {
        setJudgeMode(cloneData.judgeMode);
      }
      if (cloneData.modelIds) {
        setSelectedModels(cloneData.modelIds);
      }
      if (cloneData.judgeIds) {
        setSelectedJudges(cloneData.judgeIds);
      }
    } else if (rejudgeData) {
      // Re-judge: pre-fill name, criteria, judge mode, models, and judges
      // Questions come from the parent run (backend deep-copies them)
      setName(rejudgeData.name);
      setCriteria(rejudgeData.criteria);
      if (rejudgeData.judgeMode === 'comparison' || rejudgeData.judgeMode === 'separate') {
        setJudgeMode(rejudgeData.judgeMode);
      }
      if (rejudgeData.modelIds) {
        setSelectedModels(rejudgeData.modelIds);
      }
      if (rejudgeData.judgeIds) {
        setSelectedJudges(rejudgeData.judgeIds);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filter out archived/deleted models from cloned selections once model list loads
  useEffect(() => {
    if (models.length > 0 && cloneData) {
      const activeIds = new Set(models.map(m => m.id));
      setSelectedModels(prev => prev.filter(id => activeIds.has(id)));
      setSelectedJudges(prev => prev.filter(id => activeIds.has(id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models]);

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => benchmarksApi.create(data),
    onSuccess: (res) => {
      navigate(`/runs/${res.data.id}/live`);
    },
    onError: (error: unknown) => {
      const e = error as { response?: { data?: { detail?: string } }; message?: string };
      console.error('Failed to create benchmark:', error);
      toast.error(`Failed to create benchmark: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`);
    },
  });

  const handleModelToggle = (id: number, list: number[], setter: (ids: number[]) => void) => {
    if (list.includes(id)) {
      setter(list.filter((m) => m !== id));
    } else {
      setter([...list, id]);
    }
  };

  const addQuestion = () => {
    setQuestions([...questions, { system_prompt: '', user_prompt: '', attachment_ids: [] }]);
  };

  const removeQuestion = (index: number) => {
    setQuestions(questions.filter((_, i) => i !== index));
    // Remove attachments tracking for this question
    setQuestionAttachments(prev => {
      const updated = { ...prev };
      delete updated[index];
      // Reindex remaining attachments
      const reindexed: Record<number, Attachment[]> = {};
      Object.keys(updated).forEach(key => {
        const idx = parseInt(key);
        if (idx > index) {
          reindexed[idx - 1] = updated[idx];
        } else {
          reindexed[idx] = updated[idx];
        }
      });
      return reindexed;
    });
  };

  const updateQuestion = (index: number, field: 'system_prompt' | 'user_prompt' | 'expected_answer', value: string) => {
    const updated = [...questions];
    updated[index][field] = value;
    setQuestions(updated);
  };

  const generateQuestions = async () => {
    if (aiModelIds.length === 0 || !aiTopic) return;
    setIsGenerating(true);

    const allQuestions: Question[] = [];
    const perModelCount = Math.ceil(aiCount / aiModelIds.length);

    try {
      for (const modelId of aiModelIds) {
        const res = await questionsApi.generate({
          model_id: modelId,
          topic: aiTopic,
          count: perModelCount,
          context_attachment_id: aiContextAttachment?.id,
        });
        allQuestions.push(...res.data.questions);
      }
      setQuestions(allQuestions.slice(0, aiCount));
      setActiveTab('manual');
    } catch {
      toast.error('Failed to generate questions');
    }
    setIsGenerating(false);
  };

  const generateCriteria = async () => {
    const hasQuestions = questions.some(q => q.user_prompt.trim() || q.system_prompt.trim());
    if (!criteriaTopic && !hasQuestions) {
      toast.error('Please enter a topic or add questions first');
      return;
    }
    if (selectedJudges.length === 0) {
      toast.error('Please select a judge model first');
      return;
    }

    setIsGeneratingCriteria(true);
    try {
      // Build questions with their attachment IDs for context
      const questionsForContext = questions
        .filter(q => q.user_prompt.trim() || q.system_prompt.trim())
        .map(q => ({
          system_prompt: q.system_prompt,
          user_prompt: q.user_prompt,
          attachment_ids: q.attachment_ids || [],
        }));
      const globalAttachmentIds = globalAttachments.map(a => a.id);

      const res = await criteriaApi.generate(
        selectedJudges[0],
        criteriaTopic,
        criteriaCount,
        questionsForContext,
        globalAttachmentIds
      );
      setCriteria(res.data.criteria);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg = e?.response?.data?.detail || e?.message || 'Unknown error';
      toast.error(`Failed to generate criteria: ${errorMsg}`);
      console.error('Criteria generation error:', err);
    } finally {
      setIsGeneratingCriteria(false);
    }
  };

  const loadSuite = async (suiteId: number) => {
    try {
      const res = await suitesApi.get(suiteId);
      const suite = res.data;

      // Include expected_answer when mapping suite items to questions
      const suiteQuestions = suite.items.map((item: { system_prompt: string; user_prompt: string; expected_answer?: string | null }) => ({
        system_prompt: item.system_prompt,
        user_prompt: item.user_prompt,
        expected_answer: item.expected_answer || null,
        attachment_ids: [] as number[],
      }));

      // Load suite attachments and populate questions + display state
      try {
        const attachRes = await attachmentsApi.listSuiteAttachments(suiteId);
        const suiteAttachments = attachRes.data;
        const newGlobal: Attachment[] = [];
        const newPerQuestion: Record<number, Attachment[]> = {};

        for (const sa of suiteAttachments) {
          if (sa.scope === 'all_questions') {
            newGlobal.push(sa.attachment);
          } else if (sa.scope === 'specific' && sa.suite_item_order != null) {
            const idx = sa.suite_item_order;
            if (idx < suiteQuestions.length) {
              suiteQuestions[idx].attachment_ids.push(sa.attachment_id);
              newPerQuestion[idx] = [...(newPerQuestion[idx] || []), sa.attachment];
            }
          }
        }

        setGlobalAttachments(newGlobal);
        setQuestionAttachments(newPerQuestion);
      } catch {
        // Attachments are optional — continue without them
        setGlobalAttachments([]);
        setQuestionAttachments({});
      }

      setQuestions(suiteQuestions);
      setSourceSuiteId(suiteId);  // Track the loaded suite
      setActiveTab('manual');

      // Pre-fill run name from suite name (user can still change it at step 4)
      setName(suite.name);

      // Auto-populate criteria if the suite has defaults
      if (suite.default_criteria && suite.default_criteria.length > 0) {
        setCriteria(suite.default_criteria);
        setSuiteCriteriaLoaded(suite.name);
      } else {
        setSuiteCriteriaLoaded(null);
      }
    } catch {
      toast.error('Failed to load suite');
    }
  };

  useEffect(() => {
    if (suiteId) {
      loadSuite(suiteId);
      setStep(2);
    }
  }, [suiteId]);

  const addCriterion = () => {
    setCriteria([...criteria, { name: '', description: '', weight: 1 }]);
  };

  const removeCriterion = (index: number) => {
    setCriteria(criteria.filter((_, i) => i !== index));
  };

  const updateCriterion = (index: number, field: keyof Criterion, value: string | number) => {
    const updated = [...criteria];
    updated[index] = { ...updated[index], [field]: value };
    setCriteria(updated);
  };

  const handleSubmit = () => {
    const validCriteria = criteria.filter((c) => c.name && c.description);

    if (rejudgeData) {
      // Re-judge mode: no questions needed from the form (backend copies from parent)
      if (!name || selectedModels.length < 1 || selectedJudges.length < 1) {
        toast.error('Please fill in all required fields');
        return;
      }
      createMutation.mutate({
        name,
        model_ids: selectedModels,
        judge_ids: selectedJudges,
        judge_mode: judgeMode,
        questions: [],  // backend will deep-copy from parent run
        criteria: validCriteria,
        temperature,
        temperature_mode: temperatureMode,
        parent_run_id: rejudgeData.parentRunId,
      });
      return;
    }

    const validQuestions = questions.filter((q) => q.system_prompt && q.user_prompt);

    if (!name || selectedModels.length < 1 || selectedJudges.length < 1 || validQuestions.length < 1) {
      toast.error('Please fill in all required fields');
      return;
    }

    const globalAttachmentIds = globalAttachments.map(a => a.id);

    createMutation.mutate({
      name,
      model_ids: selectedModels,
      judge_ids: selectedJudges,
      judge_mode: judgeMode,
      questions: validQuestions.map(q => ({
        system_prompt: q.system_prompt,
        user_prompt: q.user_prompt,
        expected_answer: q.expected_answer || null,
        attachment_ids: [...globalAttachmentIds, ...(q.attachment_ids || [])]
      })),
      criteria: validCriteria,
      temperature,
      temperature_mode: temperatureMode,
      source_suite_id: sourceSuiteId,
      sequential_mode: sequentialMode,
    });
  };

  const canProceed = () => {
    switch (step) {
      case 1: return selectedModels.length >= 1;
      case 2:
        // In rejudge mode, questions come from the parent run — skip validation
        if (rejudgeData) return true;
        return questions.some((q) => q.system_prompt && q.user_prompt);
      case 3: return selectedJudges.length >= 1 && criteria.some((c) => c.name && c.description) && !selectedModels.some(id => selectedJudges.includes(id));
      case 4: return name.length > 0;
      default: return true;
    }
  };

  const getStepHint = (): string | null => {
    switch (step) {
      case 1: return selectedModels.length === 0 ? 'Select at least 1 model to continue' : null;
      case 2: return !questions.some((q) => q.system_prompt && q.user_prompt)
        ? 'Add at least 1 question with both system and user prompts' : null;
      case 3: {
        if (selectedJudges.length === 0) return 'Select at least 1 judge model';
        if (!criteria.some((c) => c.name && c.description)) return 'Add at least 1 criterion with name and description';
        if (selectedModels.some(id => selectedJudges.includes(id))) return 'Judge models cannot overlap with test models';
        return null;
      }
      case 4: return name.length === 0 ? 'Enter a benchmark name' : null;
      default: return null;
    }
  };

  const navigationButtons = (
    <div className="flex justify-between items-center">
      <Button
        variant="outline"
        onClick={() => setStep(step - 1)}
        disabled={step === 1}
      >
        &larr; Back
      </Button>

      <div className="flex items-center gap-3">
        {getStepHint() && (
          <span className="text-sm text-amber-600 dark:text-amber-400">{getStepHint()}</span>
        )}
        {step < 4 ? (
          <Button data-testid="wizard-next" onClick={() => setStep(step + 1)} disabled={!canProceed()}>
            Next &rarr;
          </Button>
        ) : (
          <Button data-testid="wizard-start" onClick={handleSubmit} disabled={createMutation.isPending || !canProceed()}>
            {createMutation.isPending ? 'Starting...' : 'Start Benchmark'}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-3xl font-bold">New Benchmark Run</h1>

      {/* Re-judge mode banner */}
      {rejudgeData && (
        <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-700 rounded-lg p-4">
          <p className="text-blue-800 dark:text-blue-200 font-medium text-sm">
            ⚖️ Re-judge mode — questions and model responses will be copied from run #{rejudgeData.parentRunId}.
            You can change judges and criteria below.
          </p>
        </div>
      )}

      {/* Progress indicator */}
      <div className="flex gap-2">
        {[1, 2, 3, 4].map((s) => (
          <div
            key={s}
            className={`flex-1 h-2 rounded ${s <= step ? 'bg-green-500' : 'bg-stone-200 dark:bg-gray-700'}`}
          />
        ))}
      </div>

      {/* Top navigation buttons */}
      {navigationButtons}

      {/* Step 1: Select Models */}
      {step === 1 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Step 1: Select Models to Test</span>
              {selectedModels.length > 0 && (
                <span className="text-sm font-normal text-green-600 dark:text-green-400">
                  {selectedModels.length} selected
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {models.length === 0 ? (
              <p className="text-slate-500 dark:text-gray-400">No models configured. Add models first.</p>
            ) : (
              <>
                {/* Filter controls */}
                <div className="flex flex-col gap-3 p-3 bg-white dark:bg-gray-900 rounded-lg">
                  {/* Search - full width */}
                  <div className="relative w-full">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-gray-500" />
                    <Input
                      placeholder="Search models..."
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                      className="pl-9 bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 w-full"
                    />
                  </div>

                  {/* Filters row - wrap on small screens */}
                  <div className="flex flex-wrap gap-2">
                    {/* Provider filter */}
                    <Select value={providerFilter} onValueChange={setProviderFilter}>
                      <SelectTrigger className="w-full sm:w-[140px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter by provider">
                        <Filter className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                        <SelectValue placeholder="Provider" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Providers</SelectItem>
                        {providers.map((p: string) => (
                          <SelectItem key={p} value={p}>
                            {p.charAt(0).toUpperCase() + p.slice(1)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {/* Reasoning filter */}
                    <Select value={reasoningFilter} onValueChange={(v) => setReasoningFilter(v as NewRunReasoningFilter)}>
                      <SelectTrigger className="w-full sm:w-[140px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter by reasoning type">
                        <Brain className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                        <SelectValue placeholder="Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Types</SelectItem>
                        <SelectItem value="reasoning">Reasoning</SelectItem>
                        <SelectItem value="standard">Standard</SelectItem>
                      </SelectContent>
                    </Select>

                    {/* Selection filter */}
                    <Select value={selectionFilter} onValueChange={(v) => setSelectionFilter(v as NewRunSelectionFilter)}>
                      <SelectTrigger className="w-full sm:w-[150px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter model selection">
                        <Filter className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                        <SelectValue placeholder="Selection" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Selection</SelectItem>
                        <SelectItem value="selected">Selected Only</SelectItem>
                        <SelectItem value="unselected">Unselected Only</SelectItem>
                      </SelectContent>
                    </Select>

                    {/* Vision filter */}
                    <Select value={visionFilter} onValueChange={(v) => setVisionFilter(v as NewRunVisionFilter)}>
                      <SelectTrigger className="w-full sm:w-[140px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter by vision capability">
                        <Eye className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                        <SelectValue placeholder="Vision" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Models</SelectItem>
                        <SelectItem value="vision">Vision Only</SelectItem>
                        <SelectItem value="non-vision">Non-Vision</SelectItem>
                      </SelectContent>
                    </Select>

                    {/* Sort */}
                    <Select value={sortBy} onValueChange={(v) => setSortBy(v as NewRunSortBy)}>
                      <SelectTrigger className="w-full sm:w-[130px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Sort models by">
                        <ArrowUpDown className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                        <SelectValue placeholder="Sort" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="frequency">By Frequency</SelectItem>
                        <SelectItem value="provider">By Provider</SelectItem>
                        <SelectItem value="name">By Name</SelectItem>
                        <SelectItem value="reasoning">By Reasoning</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Results count */}
                <div className="text-sm text-slate-500 dark:text-gray-400">
                  Showing {filteredModels.length} of {models.length} models
                </div>

                {/* Model list */}
                <div className="grid gap-2 max-h-[400px] overflow-y-auto pr-2">
                  {filteredModels.map((model) => (
                    <label
                      key={model.id}
                      data-testid={`model-card-${model.id}`}
                      className={`flex items-center gap-3 p-4 rounded cursor-pointer transition-colors ${
                        selectedModels.includes(model.id) ? 'bg-green-900/30 border border-green-500' : 'bg-white dark:bg-gray-900 border border-stone-200 dark:border-gray-700 hover:border-stone-300 dark:hover:border-gray-600'
                      }`}
                    >
                      <input
                        type="checkbox"
                        data-testid={`model-checkbox-${model.id}`}
                        checked={selectedModels.includes(model.id)}
                        onChange={() => handleModelToggle(model.id, selectedModels, setSelectedModels)}
                        className="w-5 h-5 min-w-[20px]"
                      />
                      <ProviderLogo provider={model.provider} size="md" />
                      <div className="flex-1">
                        <div className="font-medium flex items-center gap-2">
                          {model.name}
                          {model.is_reasoning && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">
                              <Brain className="w-3 h-3" />
                              <span className="font-medium">{model.reasoning_level || 'on'}</span>
                            </span>
                          )}
                          {(model.quantization || model.model_format) && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-slate-700/50 text-slate-300 rounded">
                              {model.model_format && <span>{model.model_format}</span>}
                              {model.model_format && model.quantization && <span>·</span>}
                              {model.quantization && <span>{model.quantization}</span>}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-gray-400">
                          {model.provider}
                          {getHostLabel(model.base_url) && <span className="text-slate-500 dark:text-gray-400"> · {getHostLabel(model.base_url)}</span>}
                          {' '} • {model.model_id}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {getCompactModelMetadata(model).map((item) => (
                            <span
                              key={item.key}
                              title={item.title}
                              className="inline-flex items-center rounded bg-slate-100 dark:bg-slate-700/40 px-1.5 py-0.5 text-[11px] text-slate-600 dark:text-slate-300"
                            >
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </>
            )}

            <div className="mt-6 space-y-4 p-4 bg-white dark:bg-gray-900 rounded-lg border border-stone-200 dark:border-gray-700">
              <div>
                <Label className="text-sm font-medium">Temperature Mode</Label>
                <Select value={temperatureMode} onValueChange={(v) => setTemperatureMode(v as 'normalized' | 'provider_default' | 'custom')}>
                  <SelectTrigger className="mt-2 bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Temperature mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                    <SelectItem value="normalized">{getTemperatureModeLabel('normalized')}</SelectItem>
                    <SelectItem value="provider_default">{getTemperatureModeLabel('provider_default')}</SelectItem>
                    <SelectItem value="custom">{getTemperatureModeLabel('custom')}</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">
                  {temperatureMode === 'normalized' && getTemperatureModeDescription('normalized')}
                  {temperatureMode === 'provider_default' && getTemperatureModeDescription('provider_default')}
                  {temperatureMode === 'custom' && getTemperatureModeDescription('custom')}
                </p>
              </div>

              {temperatureMode === 'normalized' && (
                <div className="space-y-2">
                  <Label className="flex items-center justify-between">
                    <span>Base Temperature</span>
                    <span className="text-sm text-slate-500 dark:text-gray-400">{temperature.toFixed(1)}</span>
                  </Label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={temperature}
                    onChange={(e) => setTemperature(Number(e.target.value))}
                    className="w-full h-2 bg-stone-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500"
                    aria-label="Base temperature"
                  />
                  <p className="text-xs text-slate-500 dark:text-gray-400">
                    Normalized across providers: 0 = deterministic, 2 = very creative
                  </p>
                </div>
              )}

              <div className="flex items-center gap-2 mt-2">
                <input
                  type="checkbox"
                  id="sequential-mode"
                  checked={sequentialMode}
                  onChange={(e) => setSequentialMode(e.target.checked)}
                  className="h-4 w-4 rounded border-stone-300 dark:border-gray-600"
                />
                <label htmlFor="sequential-mode" className="text-sm cursor-pointer select-none">
                  Sequential mode (accurate latency)
                </label>
                <span
                  className="text-xs text-muted-foreground cursor-help"
                  title="Limits each provider to one request at a time for accurate latency measurement"
                >
                  ?
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Questions */}
      {step === 2 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>Step 2: Define Questions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Tabs value={activeTab} onValueChange={(tab) => {
              setActiveTab(tab);
              // Clear suite criteria notification when user switches to manual without a suite
              if (tab === 'manual' && !sourceSuiteId) {
                setSuiteCriteriaLoaded(null);
              }
            }}>
              <TabsList className="bg-white dark:bg-gray-900">
                <TabsTrigger value="manual">Manual Entry</TabsTrigger>
                <TabsTrigger value="suite">Load Suite</TabsTrigger>
                <TabsTrigger value="ai">AI Generate</TabsTrigger>
              </TabsList>

              <TabsContent value="suite" className="space-y-4">
                <div>
                  <Label>Select a Prompt Suite</Label>
                  {suites.length === 0 ? (
                    <p className="text-slate-500 dark:text-gray-400 text-sm mt-2">No suites available. Create one first.</p>
                  ) : (
                    <div className="space-y-2 mt-2">
                      {suites.map((suite) => (
                        <div
                          key={suite.id}
                          className="p-3 bg-white dark:bg-gray-900 border border-stone-200 dark:border-gray-700 rounded hover:border-stone-300 dark:hover:border-gray-600 cursor-pointer"
                          onClick={() => loadSuite(suite.id)}
                        >
                          <div className="font-medium">{suite.name}</div>
                          {suite.description && (
                            <div className="text-sm text-slate-500 dark:text-gray-400">{suite.description}</div>
                          )}
                          <div className="flex flex-wrap gap-2 mt-2">
                            {(suite.item_count ?? 0) > 0 && (
                              <span className="text-xs bg-stone-200 dark:bg-gray-700 text-stone-700 dark:text-gray-300 px-2 py-0.5 rounded">
                                {suite.item_count} question{suite.item_count !== 1 ? 's' : ''}
                              </span>
                            )}
                            {suite.default_criteria && suite.default_criteria.length > 0 && (
                              <span className="text-xs bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
                                {suite.default_criteria.length} criteria
                              </span>
                            )}
                            {(suite.answer_count ?? 0) > 0 && (
                              <span className="text-xs bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 px-2 py-0.5 rounded">
                                {suite.answer_count === suite.item_count ? 'answers' : `${suite.answer_count}/${suite.item_count} answers`}
                              </span>
                            )}
                            {(suite.attachment_count ?? 0) > 0 && (
                              <span className="text-xs bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded">
                                {suite.attachment_count} file{suite.attachment_count !== 1 ? 's' : ''}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {questions.length > 0 && questions[0].user_prompt && (
                  <div className="mt-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <p className="text-sm text-slate-500 dark:text-gray-400">Loaded {questions.length} questions</p>
                      <Button size="sm" variant="outline" onClick={() => setActiveTab('manual')}>
                        Edit Questions
                      </Button>
                    </div>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="manual" className="space-y-4">
                {sourceSuiteId && (
                  <p className="text-sm text-muted-foreground bg-white dark:bg-gray-900 p-3 rounded border border-stone-200 dark:border-gray-700">
                    Note: Attachments from the selected suite will be automatically included.
                  </p>
                )}

                {/* Shared attachments - apply to all questions */}
                <Card className="bg-stone-50 dark:bg-gray-900/50 border-stone-200 dark:border-gray-700 border-dashed p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <span className="font-medium text-sm">Shared Attachments</span>
                      <span className="text-xs text-slate-500 dark:text-gray-400 ml-2">Apply to all questions</span>
                    </div>
                    <AttachmentButton
                      onUpload={(attachment) => {
                        setGlobalAttachments(prev => [...prev, attachment]);
                      }}
                      size="sm"
                    />
                  </div>
                  {globalAttachments.length > 0 && (
                    <AttachmentList
                      attachments={globalAttachments.map(a => ({ ...a, inherited: false }))}
                      onRemove={(attachmentId) => {
                        setGlobalAttachments(prev => prev.filter(a => a.id !== attachmentId));
                      }}
                    />
                  )}
                </Card>

                {questions.map((q, i) => (
                  <Card key={i} className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 p-4">
                    <div className="flex justify-between mb-2">
                      <span className="font-medium">Question {i + 1}</span>
                      {questions.length > 1 && (
                        <Button size="sm" variant="ghost" onClick={() => removeQuestion(i)}>
                          Remove
                        </Button>
                      )}
                    </div>
                    <div className="space-y-3">
                      <Textarea
                        placeholder="System prompt (context for the AI)"
                        value={q.system_prompt}
                        onChange={(e) => updateQuestion(i, 'system_prompt', e.target.value)}
                        className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 min-h-[60px]"
                        rows={2}
                      />
                      <Textarea
                        placeholder="User prompt (the actual question/task)"
                        value={q.user_prompt}
                        onChange={(e) => updateQuestion(i, 'user_prompt', e.target.value)}
                        className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 min-h-[80px]"
                        rows={3}
                      />

                      <details className="mt-1">
                        <summary className="text-xs text-slate-500 dark:text-gray-400 cursor-pointer hover:text-slate-700 dark:hover:text-gray-300">
                          Reference answer (optional){q.expected_answer ? ' ✓' : ''}
                        </summary>
                        <Textarea
                          placeholder="Optional reference/expected answer for judge context"
                          value={q.expected_answer || ''}
                          onChange={(e) => updateQuestion(i, 'expected_answer', e.target.value)}
                          className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 min-h-[60px] mt-1 text-sm"
                          rows={2}
                        />
                      </details>

                      <div className="space-y-2 pt-2">
                        <Label className="text-sm text-slate-500 dark:text-gray-400">Attachments (optional)</Label>

                        <AttachmentButton
                          onUpload={(attachment) => {
                            // Add to question's attachment_ids
                            const newQuestions = [...questions];
                            newQuestions[i] = {
                              ...newQuestions[i],
                              attachment_ids: [...(newQuestions[i].attachment_ids || []), attachment.id]
                            };
                            setQuestions(newQuestions);

                            // Track attachment info for display
                            setQuestionAttachments(prev => ({
                              ...prev,
                              [i]: [...(prev[i] || []), attachment]
                            }));
                          }}
                          size="sm"
                        />

                        <AttachmentList
                          attachments={questionAttachments[i] || []}
                          onRemove={(attachmentId) => {
                            // Remove from question's attachment_ids
                            const newQuestions = [...questions];
                            newQuestions[i] = {
                              ...newQuestions[i],
                              attachment_ids: newQuestions[i].attachment_ids.filter(id => id !== attachmentId)
                            };
                            setQuestions(newQuestions);

                            // Remove from display
                            setQuestionAttachments(prev => ({
                              ...prev,
                              [i]: prev[i]?.filter(a => a.id !== attachmentId) || []
                            }));
                          }}
                        />
                      </div>
                    </div>
                  </Card>
                ))}
                <Button variant="outline" onClick={addQuestion}>+ Add Question</Button>
              </TabsContent>

              <TabsContent value="ai" className="space-y-4">
                <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
                  <div>
                    <Label>Models for Generation (select 1+)</Label>
                    <div className="grid gap-1 mt-1 max-h-32 overflow-y-auto bg-white dark:bg-gray-900 p-2 rounded border border-stone-200 dark:border-gray-700">
                      {models.map((m) => (
                        <label key={m.id} className="flex items-center gap-2 cursor-pointer hover:bg-stone-100 dark:hover:bg-gray-800 p-1 rounded">
                          <input
                            type="checkbox"
                            checked={aiModelIds.includes(m.id)}
                            onChange={() => {
                              setAiModelIds(prev =>
                                prev.includes(m.id)
                                  ? prev.filter(id => id !== m.id)
                                  : [...prev, m.id]
                              );
                            }}
                            className="w-4 h-4"
                          />
                          <ProviderLogo provider={m.provider} size="sm" />
                          <span className="text-sm flex items-center gap-1">
                          {m.name}
                          {getHostLabel(m.base_url) && <span className="text-xs text-slate-500 dark:text-gray-400">({getHostLabel(m.base_url)})</span>}
                          {m.is_reasoning && (
                            <span className="inline-flex items-center gap-0.5 px-1 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">
                              <Brain className="w-3 h-3" />
                              <span>{m.reasoning_level || 'on'}</span>
                            </span>
                          )}
                        </span>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {getCompactModelMetadata(m).map((item) => (
                            <span
                              key={item.key}
                              title={item.title}
                              className="inline-flex items-center rounded bg-slate-700/50 px-1.5 py-0.5 text-[11px] text-slate-300"
                            >
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </label>
                    ))}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <Label>Topic</Label>
                      <Input
                        value={aiTopic}
                        onChange={(e) => setAiTopic(e.target.value)}
                        placeholder="e.g., Creative writing about space"
                        className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                      />
                    </div>
                    <div>
                      <Label>Total Count</Label>
                      <Input
                        type="number"
                        min={1}
                        max={50}
                        value={aiCount}
                        onChange={(e) => setAiCount(Number(e.target.value))}
                        className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                      />
                      {aiModelIds.length > 1 && (
                        <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">
                          ~{Math.ceil(aiCount / aiModelIds.length)} per model
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-2 pt-2 border-t border-stone-200 dark:border-gray-700">
                  <Label>Context Document (optional)</Label>
                  <p className="text-xs text-muted-foreground">
                    Upload a text file to generate questions based on its content.
                  </p>
                  <AttachmentButton
                    onUpload={(attachment) => setAiContextAttachment(attachment)}
                    accept=".txt,.md"
                    size="sm"
                  />
                  {aiContextAttachment && (
                    <AttachmentList
                      attachments={[{ ...aiContextAttachment, inherited: false }]}
                      onRemove={() => setAiContextAttachment(null)}
                    />
                  )}
                </div>

                <Button onClick={generateQuestions} disabled={isGenerating || aiModelIds.length === 0 || !aiTopic}>
                  {isGenerating ? 'Generating...' : `Generate from ${aiModelIds.length} model(s)`}
                </Button>

                {questions.length > 0 && questions[0].user_prompt && (
                  <div className="mt-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <p className="text-sm text-slate-500 dark:text-gray-400">Generated {questions.length} questions</p>
                      <Button size="sm" variant="outline" onClick={() => setActiveTab('manual')}>
                        Edit Questions
                      </Button>
                    </div>
                    {questions.slice(0, 3).map((q, i) => (
                      <div key={i} className="p-2 bg-white dark:bg-gray-900 rounded text-sm">
                        <div className="text-slate-500 dark:text-gray-400 truncate">System: {q.system_prompt.substring(0, 50)}...</div>
                        <div className="truncate">User: {q.user_prompt.substring(0, 100)}...</div>
                      </div>
                    ))}
                    {questions.length > 3 && (
                      <p className="text-sm text-slate-500 dark:text-gray-400">...and {questions.length - 3} more</p>
                    )}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Judging */}
      {step === 3 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>Step 3: Configure Judging</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <Label>Judge Mode</Label>
              <Select value={judgeMode} onValueChange={(v) => setJudgeMode(v as 'comparison' | 'separate')}>
                <SelectTrigger className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 w-full sm:w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                  <SelectItem value="comparison">Comparison (Blind A/B)</SelectItem>
                  <SelectItem value="separate">Separate (Independent scoring)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-slate-500 dark:text-gray-400 mt-1">
                {judgeMode === 'comparison'
                  ? 'Models compared side-by-side with blind labels (A, B, C)'
                  : 'Each response scored independently'}
              </p>
            </div>

            <div>
              <Label className="flex items-center justify-between">
                <span>Select Judges</span>
                {selectedJudges.length > 0 && (
                  <span className="text-sm font-normal text-amber-600 dark:text-amber-400">
                    {selectedJudges.length} selected
                  </span>
                )}
              </Label>

              {/* Judge filter controls */}
              <div className="flex flex-col gap-3 p-3 bg-white dark:bg-gray-900 rounded-lg mt-2">
                {/* Search */}
                <div className="relative w-full">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-gray-500" />
                  <Input
                    placeholder="Search judges..."
                    value={judgeSearch}
                    onChange={(e) => setJudgeSearch(e.target.value)}
                    className="pl-9 bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700 w-full"
                  />
                </div>

                {/* Filters row */}
                <div className="flex flex-wrap gap-2">
                  {/* Provider filter */}
                  <Select value={judgeProviderFilter} onValueChange={setJudgeProviderFilter}>
                    <SelectTrigger className="w-full sm:w-[140px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter judges by provider">
                      <Filter className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                      <SelectValue placeholder="Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Providers</SelectItem>
                      {providers.map((p: string) => (
                        <SelectItem key={p} value={p}>
                          {p.charAt(0).toUpperCase() + p.slice(1)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Reasoning filter */}
                  <Select value={judgeReasoningFilter} onValueChange={(v) => setJudgeReasoningFilter(v as 'all' | 'reasoning' | 'standard')}>
                    <SelectTrigger className="w-full sm:w-[160px] bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700" aria-label="Filter judges by reasoning type">
                      <Brain className="w-4 h-4 mr-2 text-slate-400 dark:text-gray-500" />
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="reasoning">Thinking</SelectItem>
                      <SelectItem value="standard">Non-Thinking</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Results count */}
              <div className="text-sm text-slate-500 dark:text-gray-400 mt-2">
                Showing {filteredJudges.length} of {models.length} models
              </div>

              {/* Judge list — sorted by usage frequency */}
              <div className="grid gap-2 mt-2 max-h-[400px] overflow-y-auto pr-2">
                {filteredJudges.map((model) => {
                  const usageCount = judgeUsageCounts.get(model.id) || 0;
                  return (
                    <label
                      key={model.id}
                      data-testid={`judge-card-${model.id}`}
                      className={`flex items-center gap-3 p-4 rounded cursor-pointer transition-colors ${
                        selectedJudges.includes(model.id) ? 'bg-amber-900/30 border border-amber-500' : 'bg-white dark:bg-gray-900 border border-stone-200 dark:border-gray-700 hover:border-stone-300 dark:hover:border-gray-600'
                      }`}
                    >
                      <input
                        type="checkbox"
                        data-testid={`judge-checkbox-${model.id}`}
                        checked={selectedJudges.includes(model.id)}
                        onChange={() => handleModelToggle(model.id, selectedJudges, setSelectedJudges)}
                        className="w-5 h-5 min-w-[20px]"
                      />
                      <ProviderLogo provider={model.provider} size="md" />
                      <div className="flex-1">
                        <span className="flex items-center gap-2">
                          {model.name}
                          {model.is_reasoning && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">
                              <Brain className="w-3 h-3" />
                              <span className="font-medium">{model.reasoning_level || 'on'}</span>
                            </span>
                          )}
                          {(model.quantization || model.model_format) && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-slate-700/50 text-slate-300 rounded">
                              {model.model_format && <span>{model.model_format}</span>}
                              {model.model_format && model.quantization && <span>·</span>}
                              {model.quantization && <span>{model.quantization}</span>}
                            </span>
                          )}
                          {usageCount > 0 && (
                            <span className="text-xs text-slate-400 dark:text-gray-500">
                              used {usageCount}x
                            </span>
                          )}
                        </span>
                        <div className="text-sm text-slate-500 dark:text-gray-400">
                          {model.provider}
                          {getHostLabel(model.base_url) && <span> · {getHostLabel(model.base_url)}</span>}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Self-judging warning */}
            {selectedModels.some(id => selectedJudges.includes(id)) && (
              <div className="bg-red-900/30 border border-red-500 rounded p-3 text-red-300 text-sm">
                <strong>Self-judging detected:</strong> One or more models are selected as both competitor and judge.
                A model cannot fairly judge its own outputs. Please select different judges.
              </div>
            )}

            {/* Family overlap warning (C18 — preference leakage) */}
            {familyOverlapWarnings.length > 0 && (
              <div data-testid="family-overlap-warning" className="rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
                <strong>Family overlap detected:</strong>{' '}
                {familyOverlapWarnings[0].message}
                {familyOverlapWarnings.length > 1 && (
                  <span> (+{familyOverlapWarnings.length - 1} more pair{familyOverlapWarnings.length > 2 ? 's' : ''})</span>
                )}
              </div>
            )}

            {/* Suite criteria notification */}
            {suiteCriteriaLoaded && (
              <div className="text-sm text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/20 rounded px-3 py-2 mb-4">
                Loaded criteria from suite: {suiteCriteriaLoaded}. You can edit them below.
              </div>
            )}

            {/* AI Criteria Generator */}
            <div className="space-y-2 mt-6">
              <Label>AI Criteria Generator</Label>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  placeholder="Optional topic (e.g., creative writing, code review)"
                  value={criteriaTopic}
                  onChange={(e) => setCriteriaTopic(e.target.value)}
                  className="flex-1 bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 w-full"
                />
                <div className="flex items-center gap-1">
                  <Label className="text-xs text-slate-500 dark:text-gray-400 whitespace-nowrap">Count:</Label>
                  <Input
                    type="number"
                    min={2}
                    max={12}
                    value={criteriaCount}
                    onChange={(e) => setCriteriaCount(Math.min(12, Math.max(2, Number(e.target.value))))}
                    className="w-16 bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  />
                </div>
                <Button
                  onClick={generateCriteria}
                  disabled={isGeneratingCriteria || (!criteriaTopic && !questions.some(q => q.user_prompt.trim() || q.system_prompt.trim())) || selectedJudges.length === 0}
                  variant="secondary"
                  className="w-full sm:w-auto"
                >
                  {isGeneratingCriteria ? 'Generating...' : 'Generate'}
                </Button>
              </div>
              <p className="text-xs text-slate-500 dark:text-gray-400">Generates criteria based on your questions and attachments. Add an optional topic to guide focus.</p>
            </div>

            <div>
              <Label>Evaluation Criteria</Label>
              <div className="space-y-2 mt-2">
                {criteria.map((c, i) => (
                  <div key={i} className="flex flex-col sm:flex-row gap-2 items-start sm:items-start">
                    <Input
                      placeholder="Name"
                      value={c.name}
                      onChange={(e) => updateCriterion(i, 'name', e.target.value)}
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 w-full sm:w-32"
                    />
                    <Input
                      placeholder="Description"
                      value={c.description}
                      onChange={(e) => updateCriterion(i, 'description', e.target.value)}
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 flex-1 w-full"
                    />
                    <Input
                      type="number"
                      min={0.1}
                      max={10}
                      step={0.1}
                      value={c.weight}
                      onChange={(e) => updateCriterion(i, 'weight', Number(e.target.value))}
                      className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700 w-20"
                    />
                    {criteria.length > 1 && (
                      <Button size="sm" variant="ghost" onClick={() => removeCriterion(i)}>×</Button>
                    )}
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={addCriterion}>+ Add Criterion</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Review */}
      {step === 4 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>Step 4: Review & Start</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Benchmark Name</Label>
              <Input
                data-testid="wizard-run-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Creative Writing Test - Jan 2026"
                className="bg-white dark:bg-gray-900 border-stone-200 dark:border-gray-700"
              />
            </div>

            <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
              <div className="p-4 bg-white dark:bg-gray-900 rounded">
                <h3 className="font-medium text-green-600 dark:text-green-400 mb-2">Models ({selectedModels.length})</h3>
                {models.filter((m) => selectedModels.includes(m.id)).map((m) => (
                  <div key={m.id} className="flex items-center gap-2 py-1">
                    <ProviderLogo provider={m.provider} size="sm" />
                    <span>{m.name}</span>
                    {getHostLabel(m.base_url) && <span className="text-xs text-slate-500 dark:text-gray-400">({getHostLabel(m.base_url)})</span>}
                    {m.is_reasoning && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">
                        <Brain className="w-3 h-3" />
                        <span className="font-medium">{m.reasoning_level || 'on'}</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="p-4 bg-white dark:bg-gray-900 rounded">
                <h3 className="font-medium text-amber-600 dark:text-amber-400 mb-2">Judges ({selectedJudges.length})</h3>
                {models.filter((m) => selectedJudges.includes(m.id)).map((m) => (
                  <div key={m.id} className="flex items-center gap-2 py-1">
                    <ProviderLogo provider={m.provider} size="sm" />
                    <span>{m.name}</span>
                    {getHostLabel(m.base_url) && <span className="text-xs text-slate-500 dark:text-gray-400">({getHostLabel(m.base_url)})</span>}
                    {m.is_reasoning && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">
                        <Brain className="w-3 h-3" />
                        <span className="font-medium">{m.reasoning_level || 'on'}</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 bg-white dark:bg-gray-900 rounded space-y-1">
              <p><span className="text-slate-500 dark:text-gray-400">Questions:</span> {questions.filter(q => q.user_prompt).length}</p>
              {questions.filter(q => q.expected_answer).length > 0 && (
                <div className="text-sm text-slate-500 dark:text-gray-400">
                  {questions.filter(q => q.expected_answer).length} of {questions.length} questions have reference answers
                </div>
              )}
              <p><span className="text-slate-500 dark:text-gray-400">Judge Mode:</span> {judgeMode}</p>
              <p>
                <span className="text-slate-500 dark:text-gray-400">Temperature:</span>{' '}
                {temperatureMode === 'normalized' && `Normalized (Best-effort, base: ${temperature.toFixed(1)})`}
                {temperatureMode === 'provider_default' && getTemperatureModeLabel('provider_default')}
                {temperatureMode === 'custom' && getTemperatureModeLabel('custom')}
              </p>
              <p><span className="text-slate-500 dark:text-gray-400">Criteria:</span> {criteria.filter(c => c.name).map(c => c.name).join(', ')}</p>
              {globalAttachments.length > 0 && (
                <p>
                  <span className="text-slate-500 dark:text-gray-400">Shared Attachments:</span>{' '}
                  {globalAttachments.length} file{globalAttachments.length !== 1 ? 's' : ''} (applied to all questions)
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Bottom navigation buttons */}
      {navigationButtons}
    </div>
  );
}
