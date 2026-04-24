import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { benchmarksApi } from '@/lib/api';
import { formatISODateTime } from '@/lib/utils';
import {
  Trash2,
  Plus,
  GitCompare,
  Play,
  Eye,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Trophy,
  Search,
  ArrowUpDown,
  Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { ErrorBanner } from '@/components/ui/error-banner';
import type { BenchmarkRun } from '@/types/api';

export function Runs() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [isDeleting, setIsDeleting] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('newest');
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; ids: number[] }>({
    open: false,
    ids: []
  });

  const { data: runs = [], isLoading, error, refetch } = useQuery<BenchmarkRun[]>({
    queryKey: ['runs'],
    queryFn: async () => (await benchmarksApi.list()).data,
  });

  // Filter and sort runs
  const filteredRuns = useMemo(() => {
    let result = [...runs];

    // Search filter
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(r =>
        r.name.toLowerCase().includes(term) ||
        r.top_models.some(m => m.name.toLowerCase().includes(term))
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(r => r.status === statusFilter);
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'newest':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'oldest':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case 'name':
          return a.name.localeCompare(b.name);
        case 'cost':
          return (b.total_cost || 0) - (a.total_cost || 0);
        default:
          return 0;
      }
    });

    return result;
  }, [runs, searchTerm, statusFilter, sortBy]);

  // Calculate stats
  const stats = useMemo(() => ({
    total: runs.length,
    completed: runs.filter(r => r.status === 'completed').length,
    running: runs.filter(r => r.status === 'running').length,
    failed: runs.filter(r => r.status === 'failed').length,
    cancelled: runs.filter(r => r.status === 'cancelled').length,
  }), [runs]);

  const deleteMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) {
        await benchmarksApi.delete(id);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      setSelectedIds([]);
      setIsDeleting(false);
    },
    onError: () => {
      setIsDeleting(false);
    },
  });

  const handleDelete = () => {
    const runningRuns = runs.filter(r => selectedIds.includes(r.id) && r.status === 'running');
    if (runningRuns.length > 0) {
      toast.error(`Cannot delete running benchmarks. Cancel them first:\n${runningRuns.map(r => r.name).join('\n')}`);
      return;
    }

    setDeleteConfirm({ open: true, ids: selectedIds });
  };

  const toggleSelection = (id: number) => {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((i) => i !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  };

  const formatDate = (dateStr: string) => formatISODateTime(dateStr);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <ErrorBanner
          message={`Failed to load runs: ${error instanceof Error ? error.message : 'Unknown error'}`}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold">Benchmark Runs</h1>
          <p className="text-slate-500 dark:text-gray-400 text-sm mt-1">
            {stats.total} runs • {stats.completed} completed • {stats.running} running
          </p>
        </div>
        <Link to="/runs/new">
          <Button className="bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-white font-semibold gap-2">
            <Plus className="w-4 h-4" />
            New Run
          </Button>
        </Link>
      </div>

      {/* Quick Stats */}
      {runs.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <QuickStatCard
            icon={<CheckCircle2 className="w-4 h-4" />}
            label="Completed"
            value={stats.completed}
            color="green"
            active={statusFilter === 'completed'}
            onClick={() => setStatusFilter(statusFilter === 'completed' ? 'all' : 'completed')}
          />
          <QuickStatCard
            icon={<Play className="w-4 h-4" />}
            label="Running"
            value={stats.running}
            color="blue"
            active={statusFilter === 'running'}
            onClick={() => setStatusFilter(statusFilter === 'running' ? 'all' : 'running')}
          />
          <QuickStatCard
            icon={<XCircle className="w-4 h-4" />}
            label="Failed"
            value={stats.failed}
            color="red"
            active={statusFilter === 'failed'}
            onClick={() => setStatusFilter(statusFilter === 'failed' ? 'all' : 'failed')}
          />
          <QuickStatCard
            icon={<XCircle className="w-4 h-4" />}
            label="Cancelled"
            value={stats.cancelled}
            color="yellow"
            active={statusFilter === 'cancelled'}
            onClick={() => setStatusFilter(statusFilter === 'cancelled' ? 'all' : 'cancelled')}
          />
        </div>
      )}

      {/* Filters and Selection Actions */}
      {runs.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
          <div className="flex flex-1 gap-3 items-center">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-gray-500" />
              <Input
                placeholder="Search runs or models..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50"
              />
            </div>
            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger className="w-[140px] bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50" aria-label="Sort runs by">
                <ArrowUpDown className="w-4 h-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
                <SelectItem value="newest">Newest</SelectItem>
                <SelectItem value="oldest">Oldest</SelectItem>
                <SelectItem value="name">Name</SelectItem>
                <SelectItem value="cost">Cost</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Selection Actions */}
          {selectedIds.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-2 bg-stone-100 dark:bg-gray-800/50 rounded-lg border border-stone-200 dark:border-gray-700/50">
              <span className="text-sm text-slate-500 dark:text-gray-400">{selectedIds.length} selected</span>
              {selectedIds.length >= 2 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => navigate(`/runs/compare?ids=${selectedIds.join(',')}`)}
                  className="text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/10"
                >
                  <GitCompare className="w-4 h-4 mr-1" />
                  Compare
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={handleDelete}
                disabled={isDeleting}
                className="text-red-600 dark:text-red-400 hover:text-red-300 hover:bg-red-500/10"
              >
                <Trash2 className="w-4 h-4 mr-1" />
                Delete
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSelectedIds([])}
                className="text-slate-500 dark:text-gray-400"
              >
                Clear
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Runs List */}
      {runs.length === 0 ? (
        <EmptyState />
      ) : filteredRuns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-slate-500 dark:text-gray-400">No runs match your filters</p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
            className="mt-2 text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
          >
            Clear filters
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRuns.map((run) => (
            <RunCard
              key={run.id}
              run={run}
              selected={selectedIds.includes(run.id)}
              onToggleSelect={() => toggleSelection(run.id)}
              onNavigate={() => navigate(run.status === 'running' ? `/runs/${run.id}/live` : `/runs/${run.id}`)}
              formatDate={formatDate}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm({ open, ids: [] })}
        title="Delete Benchmark Runs"
        description={`Delete ${deleteConfirm.ids.length} benchmark run${deleteConfirm.ids.length > 1 ? 's' : ''}? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => {
          // Re-check run statuses before destructive action (may have changed since dialog opened)
          const nowRunning = runs.filter(r => deleteConfirm.ids.includes(r.id) && r.status === 'running');
          if (nowRunning.length > 0) {
            toast.error(`Cannot delete: ${nowRunning.map(r => r.name).join(', ')} started running`);
            setDeleteConfirm({ open: false, ids: [] });
            return;
          }
          setIsDeleting(true);
          deleteMutation.mutate(deleteConfirm.ids);
        }}
      />
    </div>
  );
}

// Quick Stat Card Component
function QuickStatCard({
  icon,
  label,
  value,
  color,
  active,
  onClick
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: 'green' | 'blue' | 'red' | 'gray' | 'yellow';
  active: boolean;
  onClick: () => void;
}) {
  const colorClasses = {
    green: active ? 'bg-green-500/20 border-green-500/50 text-green-400' : 'bg-green-500/5 border-green-500/20 text-green-500 hover:bg-green-500/10',
    blue: active ? 'bg-blue-500/20 border-blue-500/50 text-blue-400' : 'bg-blue-500/5 border-blue-500/20 text-blue-500 hover:bg-blue-500/10',
    red: active ? 'bg-red-500/20 border-red-500/50 text-red-400' : 'bg-red-500/5 border-red-500/20 text-red-500 hover:bg-red-500/10',
    gray: active ? 'bg-gray-500/20 border-gray-500/50 text-gray-400' : 'bg-gray-500/5 border-gray-500/20 text-gray-500 hover:bg-gray-500/10',
    yellow: active ? 'bg-yellow-500/20 border-yellow-500/50 text-yellow-400' : 'bg-yellow-500/5 border-yellow-500/20 text-yellow-500 hover:bg-yellow-500/10',
  };

  return (
    <button
      onClick={onClick}
      className={`p-3 rounded-lg border transition-all ${colorClasses[color]}`}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-xl font-bold text-gray-900 dark:text-white mt-1">{value}</p>
    </button>
  );
}

// Run Card Component
function RunCard({
  run,
  selected,
  onToggleSelect,
  onNavigate,
  formatDate
}: {
  run: BenchmarkRun;
  selected: boolean;
  onToggleSelect: () => void;
  onNavigate: () => void;
  formatDate: (date: string) => string;
}) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />;
      case 'running':
        return <div className="w-4 h-4 rounded-full border-2 border-blue-600 dark:border-blue-400 border-t-transparent animate-spin" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />;
      case 'cancelled':
        return <AlertCircle className="w-4 h-4 text-yellow-400" />;
      default:
        return <Clock className="w-4 h-4 text-slate-500 dark:text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600 dark:text-green-400';
      case 'running': return 'text-blue-600 dark:text-blue-400';
      case 'failed': return 'text-red-600 dark:text-red-400';
      case 'cancelled': return 'text-yellow-400';
      default: return 'text-slate-500 dark:text-gray-400';
    }
  };

  return (
    <Card
      className={`
        transition-all duration-200 cursor-pointer
        ${selected
          ? 'bg-amber-100 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30'
          : 'bg-stone-50 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50 hover:bg-white dark:hover:bg-gray-800/70 hover:border-stone-300 dark:hover:border-gray-600/50'
        }
      `}
    >
      <CardContent className="p-4">
        <div className="flex items-center gap-4">
          {/* Checkbox */}
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => { e.stopPropagation(); onToggleSelect(); }}
            className="w-5 h-5 rounded border-stone-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-amber-500 focus:ring-amber-500 focus:ring-offset-0 cursor-pointer"
            aria-label={`Select ${run.name}`}
          />

          {/* Status Icon */}
          <div className="hidden sm:flex items-center justify-center w-10 h-10 rounded-full bg-stone-200/50 dark:bg-gray-700/50">
            {getStatusIcon(run.status)}
          </div>

          {/* Main Info */}
          <div className="flex-1 min-w-0" onClick={onNavigate}>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-slate-800 dark:text-gray-200 truncate hover:text-amber-600 dark:hover:text-amber-400 transition-colors">
                {run.name}
              </h3>
              <span className={`text-xs font-medium uppercase ${getStatusColor(run.status)}`}>
                {run.status}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-slate-500 dark:text-gray-400">
              <span>{run.model_count} models</span>
              <span>•</span>
              <span>{run.judge_count} judges</span>
              <span>•</span>
              <span>{run.question_count} questions</span>
              <span>•</span>
              <span>{formatDate(run.created_at)}</span>
            </div>
          </div>

          {/* Top Models */}
          {run.top_models.length > 0 && (
            <div className="hidden md:flex items-center gap-2">
              <Trophy className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              <div className="flex flex-col text-xs">
                {run.top_models.slice(0, 5).map((model, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <span className={
                      i === 0 ? 'text-amber-700 dark:text-amber-300 font-medium'
                      : i === 1 ? 'text-slate-500 dark:text-gray-400'
                      : i === 2 ? 'text-amber-500'
                      : 'text-slate-400 dark:text-gray-500 text-[11px]'
                    }>
                      {model.name.length > 20 ? `${model.name.slice(0, 20)}...` : model.name}
                    </span>
                    <span className="text-amber-600 dark:text-green-400 font-mono text-[10px] tabular-nums">
                      {model.weighted_score.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cost */}
          {run.total_cost != null && (
            <div className="hidden sm:block text-right">
              <span className="text-green-600 dark:text-green-400 font-mono text-sm">
                ${run.total_cost.toFixed(4)}
              </span>
            </div>
          )}

          {/* Action Button */}
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => { e.stopPropagation(); onNavigate(); }}
            className="shrink-0 text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          >
            {run.status === 'running' ? (
              <>
                <Zap className="w-4 h-4 mr-1 text-blue-600 dark:text-blue-400" />
                Live
              </>
            ) : (
              <>
                <Eye className="w-4 h-4 mr-1" />
                View
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Empty State Component
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-20 h-20 rounded-full bg-gradient-to-br from-amber-500/20 to-orange-500/10 flex items-center justify-center mb-6">
        <Zap className="w-10 h-10 text-amber-600 dark:text-amber-400" />
      </div>
      <h3 className="text-xl font-semibold text-slate-800 dark:text-gray-200 mb-2">No benchmark runs yet</h3>
      <p className="text-slate-500 dark:text-gray-400 mb-6 max-w-md">
        Start your first benchmark to compare how different LLMs perform on your questions and criteria.
      </p>
      <Link to="/runs/new">
        <Button className="bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-white font-semibold gap-2">
          <Plus className="w-4 h-4" />
          Create Your First Benchmark
        </Button>
      </Link>
    </div>
  );
}
