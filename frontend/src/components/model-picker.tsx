import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search, X } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { ModelPreset } from '../types/api.js';
import {
  filterSuiteModels,
  formatSuiteModelLabel,
  formatSuiteModelMeta,
  sortSuiteModels,
} from '@/pages/suites/modelSelection';

export interface ModelPickerProps {
  models: ModelPreset[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  multiple?: boolean;
  placeholder: string;
  disabled?: boolean;
  maxSelections?: number;
  excludeIds?: number[];
}

function buildSelectionSummary(
  selectedModels: ModelPreset[],
  multiple: boolean,
  placeholder: string,
): string {
  if (selectedModels.length === 0) {
    return placeholder;
  }

  if (!multiple) {
    return formatSuiteModelLabel(selectedModels[0]);
  }

  if (selectedModels.length === 1) {
    return formatSuiteModelLabel(selectedModels[0]);
  }

  if (selectedModels.length === 2) {
    return `${formatSuiteModelLabel(selectedModels[0])}, ${formatSuiteModelLabel(selectedModels[1])}`;
  }

  return `${formatSuiteModelLabel(selectedModels[0])}, ${formatSuiteModelLabel(selectedModels[1])} +${selectedModels.length - 2}`;
}

export function ModelPicker({
  models,
  selectedIds,
  onChange,
  multiple = false,
  placeholder,
  disabled = false,
  maxSelections,
  excludeIds = [],
}: ModelPickerProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const selectableModels = useMemo(
    () => sortSuiteModels(models.filter((model) => !excludeIds.includes(model.id))),
    [excludeIds, models],
  );
  const visibleModels = useMemo(
    () => filterSuiteModels(selectableModels, query),
    [query, selectableModels],
  );
  const selectedModels = selectedIds
    .map((id) => models.find((model) => model.id === id))
    .filter((model): model is ModelPreset => model != null);
  const selectionSummary = buildSelectionSummary(selectedModels, multiple, placeholder);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    searchInputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (containerRef.current?.contains(event.target as Node)) {
        return;
      }
      setQuery('');
      setIsOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setQuery('');
        setIsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleSelect = (modelId: number) => {
    if (disabled) return;

    if (multiple) {
      if (selectedIds.includes(modelId)) {
        onChange(selectedIds.filter((id) => id !== modelId));
        return;
      }

      if (maxSelections != null && selectedIds.length >= maxSelections) {
        return;
      }

      onChange([...selectedIds, modelId]);
      return;
    }

    onChange([modelId]);
    setQuery('');
    setIsOpen(false);
  };

  const handleClear = () => {
    if (disabled) return;
    onChange([]);
    setQuery('');
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            setIsOpen((open) => {
              const nextOpen = !open;
              if (!nextOpen) {
                setQuery('');
              }
              return nextOpen;
            })
          }
          aria-expanded={isOpen}
          className={cn(
            'flex h-12 w-full items-center rounded-md border bg-white px-3 py-2 pr-20 text-left text-sm shadow-sm transition-colors',
            'border-stone-200 dark:border-gray-700 dark:bg-gray-950',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          <span
            className={cn(
              'truncate',
              selectedModels.length === 0 && 'text-slate-500 dark:text-gray-400',
            )}
          >
            {selectionSummary}
          </span>
        </button>
        {selectedIds.length > 0 && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-10 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-stone-100 hover:text-slate-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </button>
        )}
        <ChevronDown
          className={cn(
            'pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 transition-transform dark:text-gray-400',
            isOpen && 'rotate-180',
          )}
        />
      </div>

      {isOpen && (
        <div className="absolute left-0 right-0 z-50 mt-2 overflow-hidden rounded-lg border border-stone-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
          <div className="border-b border-stone-200 p-2 dark:border-gray-700">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-gray-400" />
              <Input
                ref={searchInputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
                disabled={disabled}
                aria-label={placeholder}
                className="border-stone-200 bg-white pl-9 pr-9 dark:border-gray-700 dark:bg-gray-950"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="absolute right-3 top-1/2 inline-flex h-4 w-4 -translate-y-1/2 items-center justify-center text-slate-500 hover:text-slate-900 dark:text-gray-400 dark:hover:text-white"
                  aria-label="Clear search"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto">
            {visibleModels.length === 0 ? (
              <p className="px-3 py-4 text-sm text-slate-500 dark:text-gray-400">
                No models match "{query.trim()}"
              </p>
            ) : (
              <ul>
                {visibleModels.map((model) => {
                  const selected = selectedIds.includes(model.id);
                  const atLimit =
                    multiple &&
                    maxSelections != null &&
                    selectedIds.length >= maxSelections &&
                    !selected;

                  return (
                    <li key={model.id} className="border-b border-stone-100 last:border-b-0 dark:border-gray-800">
                      <button
                        type="button"
                        disabled={disabled || atLimit}
                        onClick={() => handleSelect(model.id)}
                        className={cn(
                          'flex h-11 w-full items-center gap-3 px-3 text-left text-sm transition-colors',
                          selected
                            ? 'bg-blue-50 text-blue-900 dark:bg-blue-950/40 dark:text-blue-100'
                            : 'hover:bg-stone-50 dark:hover:bg-gray-800',
                          disabled && 'cursor-not-allowed opacity-60',
                          atLimit && 'cursor-not-allowed opacity-50',
                        )}
                      >
                        <span className="min-w-0 flex-1 truncate font-medium">
                          {formatSuiteModelLabel(model)}
                        </span>
                        <span className="hidden min-w-0 flex-1 truncate text-xs text-slate-500 dark:text-gray-400 md:block">
                          {formatSuiteModelMeta(model)}
                        </span>
                        <span className="flex shrink-0 items-center gap-2 text-xs text-slate-500 dark:text-gray-400">
                          {selected && <Check className="h-4 w-4 text-blue-600 dark:text-blue-300" />}
                          <span>{selected ? 'Selected' : multiple ? 'Add' : 'Select'}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {multiple && (
            <div className="border-t border-stone-200 px-3 py-2 text-xs text-slate-500 dark:border-gray-700 dark:text-gray-400">
              {selectedIds.length} selected
              {maxSelections != null ? ` · max ${maxSelections}` : ''}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
