import { useState, useRef, useEffect } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SectionId } from './useResultsNav';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

interface SidebarProps {
  activeSection: SectionId;
  onNavigate: (section: SectionId) => void;
  modelNames: string[];
  questionCount: number;
  slugify: (s: string) => string;
  parentRunId?: number | null;
}

const STATIC_SECTIONS: Array<{ id: SectionId; label: string; emoji: string }> = [
  { id: 'overview', label: 'Overview', emoji: '📊' },
  { id: 'charts', label: 'Charts', emoji: '📈' },
  { id: 'scores', label: 'Scores', emoji: '🎯' },
  { id: 'statistics', label: 'Statistics', emoji: '🔬' },
  { id: 'judges', label: 'Judges', emoji: '⚖️' },
];

const HIGHLIGHT_SECTIONS: Array<{ id: SectionId; label: string; emoji: string }> = [
  { id: 'best-answers', label: 'Best Answers', emoji: '🏆' },
  { id: 'worst-answers', label: 'Worst Answers', emoji: '💩' },
  { id: 'judge-disagreement', label: 'Judge Disputes', emoji: '⚔️' },
];

function NavButton({
  label,
  isActive,
  onClick,
  className,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left px-3 py-1.5 rounded text-sm transition-colors',
        isActive
          ? 'bg-stone-200 dark:bg-gray-700 text-gray-900 dark:text-white font-medium'
          : 'text-slate-500 dark:text-gray-400 hover:bg-stone-100 dark:hover:bg-gray-800 hover:text-slate-800 dark:hover:text-gray-200',
        className
      )}
    >
      {label}
    </button>
  );
}

function CollapsibleGroup({
  title,
  defaultOpen,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-sm font-semibold text-slate-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
      >
        <span>{title}</span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 shrink-0" />
        )}
      </button>
      {open && <div className="pl-2 flex flex-col gap-0.5">{children}</div>}
    </div>
  );
}

export function ResultsSidebar({
  activeSection,
  onNavigate,
  modelNames,
  questionCount,
  slugify,
  parentRunId,
}: SidebarProps) {
  const modelsOpen = activeSection.startsWith('model-');
  const questionsOpen = activeSection.startsWith('question-');

  return (
    <nav className={cn("w-[200px] shrink-0 sticky top-[170px] self-start max-h-[calc(100vh-11rem)] overflow-y-auto", DEMO_MODE ? "hidden" : "hidden lg:block")}>
      <div className="flex flex-col gap-0.5">
        {STATIC_SECTIONS.map(({ id, label, emoji }) => (
          <NavButton
            key={id}
            label={`${emoji} ${label}`}
            isActive={activeSection === id}
            onClick={() => onNavigate(id)}
          />
        ))}
        {parentRunId && (
          <NavButton
            label="🔀 Compare Parent"
            isActive={activeSection === 'compare-parent'}
            onClick={() => onNavigate('compare-parent')}
          />
        )}

        <div className="mt-2">
          <CollapsibleGroup
            title="Highlights"
            defaultOpen={HIGHLIGHT_SECTIONS.some(s => s.id === activeSection)}
          >
            {HIGHLIGHT_SECTIONS.map(({ id, label, emoji }) => (
              <NavButton
                key={id}
                label={`${emoji} ${label}`}
                isActive={activeSection === id}
                onClick={() => onNavigate(id)}
              />
            ))}
          </CollapsibleGroup>
        </div>

        {modelNames.length > 0 && (
          <div className="mt-2">
            <CollapsibleGroup title="Models" defaultOpen={modelsOpen}>
              {modelNames.map((name) => {
                const sectionId: SectionId = `model-${slugify(name)}`;
                return (
                  <NavButton
                    key={sectionId}
                    label={name}
                    isActive={activeSection === sectionId}
                    onClick={() => onNavigate(sectionId)}
                  />
                );
              })}
            </CollapsibleGroup>
          </div>
        )}

        {questionCount > 0 && (
          <div className="mt-1">
            <CollapsibleGroup title="Questions" defaultOpen={questionsOpen}>
              {Array.from({ length: questionCount }, (_, i) => {
                const sectionId: SectionId = `question-${i}`;
                return (
                  <NavButton
                    key={sectionId}
                    label={`Q${i + 1}`}
                    isActive={activeSection === sectionId}
                    onClick={() => onNavigate(sectionId)}
                  />
                );
              })}
            </CollapsibleGroup>
          </div>
        )}
      </div>
    </nav>
  );
}

export function ResultsDropdownNav({
  activeSection,
  onNavigate,
  modelNames,
  questionCount,
  slugify,
  parentRunId,
}: SidebarProps) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Resolve active label
  const activeLabel = (() => {
    const staticMatch = STATIC_SECTIONS.find(s => s.id === activeSection);
    if (staticMatch) return `${staticMatch.emoji} ${staticMatch.label}`;
    const highlightMatch = HIGHLIGHT_SECTIONS.find(s => s.id === activeSection);
    if (highlightMatch) return `${highlightMatch.emoji} ${highlightMatch.label}`;
    if (activeSection === 'compare-parent') return '🔀 Compare Parent';
    if (activeSection.startsWith('model-')) {
      const slug = activeSection.replace('model-', '');
      const name = modelNames.find(n => slugify(n) === slug);
      return name ?? 'Model';
    }
    if (activeSection.startsWith('question-')) {
      const idx = parseInt(activeSection.replace('question-', ''), 10);
      return `Q${idx + 1}`;
    }
    return '📊 Overview';
  })();

  const handleNav = (section: SectionId) => {
    onNavigate(section);
    setOpen(false);
  };

  const modelsOpen = activeSection.startsWith('model-');
  const questionsOpen = activeSection.startsWith('question-');

  return (
    <div ref={dropdownRef} className={cn("relative", !DEMO_MODE && "lg:hidden")}>
      {/* Trigger chip */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-stone-200 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-stone-300 dark:hover:bg-gray-600 transition-colors"
      >
        {activeLabel}
        <ChevronDown className={cn('w-3.5 h-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute left-0 top-full mt-1 w-[min(280px,90vw)] max-h-[60vh] overflow-y-auto bg-white dark:bg-gray-800 border border-stone-200 dark:border-gray-700 rounded-lg shadow-lg z-30">
          <div className="py-1">
            {/* Static sections */}
            {STATIC_SECTIONS.map(({ id, label, emoji }) => (
              <button
                key={id}
                onClick={() => handleNav(id)}
                className={cn(
                  'w-full text-left px-3 py-2 text-sm transition-colors',
                  activeSection === id
                    ? 'bg-stone-100 dark:bg-gray-700 text-gray-900 dark:text-white font-medium'
                    : 'text-slate-600 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-700'
                )}
              >
                {emoji} {label}
              </button>
            ))}

            {/* Compare Parent (spin-offs only) */}
            {parentRunId && (
              <button
                onClick={() => handleNav('compare-parent')}
                className={cn(
                  'w-full text-left px-3 py-2 text-sm transition-colors',
                  activeSection === 'compare-parent'
                    ? 'bg-stone-100 dark:bg-gray-700 text-gray-900 dark:text-white font-medium'
                    : 'text-slate-600 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-700'
                )}
              >
                🔀 Compare Parent
              </button>
            )}

            {/* Highlights group */}
            <div className="border-t border-stone-200 dark:border-gray-700 my-1" />
            <CollapsibleGroup
              title="Highlights"
              defaultOpen={HIGHLIGHT_SECTIONS.some(s => s.id === activeSection)}
            >
              {HIGHLIGHT_SECTIONS.map(({ id, label, emoji }) => (
                <button
                  key={id}
                  onClick={() => handleNav(id)}
                  className={cn(
                    'w-full text-left px-3 py-1.5 text-sm transition-colors',
                    activeSection === id
                      ? 'bg-stone-100 dark:bg-gray-700 text-gray-900 dark:text-white font-medium'
                      : 'text-slate-600 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-700'
                  )}
                >
                  {emoji} {label}
                </button>
              ))}
            </CollapsibleGroup>

            {/* Models group */}
            {modelNames.length > 0 && (
              <>
                <div className="border-t border-stone-200 dark:border-gray-700 my-1" />
                <CollapsibleGroup title="Models" defaultOpen={modelsOpen}>
                  {modelNames.map((name) => {
                    const sectionId: SectionId = `model-${slugify(name)}`;
                    return (
                      <button
                        key={sectionId}
                        onClick={() => handleNav(sectionId)}
                        className={cn(
                          'w-full text-left px-3 py-1.5 text-sm transition-colors',
                          activeSection === sectionId
                            ? 'bg-stone-100 dark:bg-gray-700 text-gray-900 dark:text-white font-medium'
                            : 'text-slate-600 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-700'
                        )}
                      >
                        {name}
                      </button>
                    );
                  })}
                </CollapsibleGroup>
              </>
            )}

            {/* Questions group */}
            {questionCount > 0 && (
              <>
                <div className="border-t border-stone-200 dark:border-gray-700 my-1" />
                <CollapsibleGroup title="Questions" defaultOpen={questionsOpen}>
                  <div className="flex flex-wrap gap-1 px-3 py-1">
                    {Array.from({ length: questionCount }, (_, i) => {
                      const sectionId: SectionId = `question-${i}`;
                      return (
                        <button
                          key={sectionId}
                          onClick={() => handleNav(sectionId)}
                          className={cn(
                            'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                            activeSection === sectionId
                              ? 'bg-stone-200 dark:bg-gray-600 text-gray-900 dark:text-white'
                              : 'bg-stone-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 hover:bg-stone-200 dark:hover:bg-gray-600'
                          )}
                        >
                          Q{i + 1}
                        </button>
                      );
                    })}
                  </div>
                </CollapsibleGroup>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
