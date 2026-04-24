import type { QuestionBrowserMatchFidelity, QuestionBrowserSearchRow } from '@/types/api';

export interface QuestionBrowserExplorerQuestion extends QuestionBrowserSearchRow {
  isActive: boolean;
}

export interface QuestionBrowserExplorerGroup {
  runId: number;
  runName: string;
  matchCount: number;
  previewQuestionId: number;
  previewText: string;
  hasDegradedMatch: boolean;
  questions: QuestionBrowserExplorerQuestion[];
}

export interface QuestionBrowserExplorerState {
  groups: QuestionBrowserExplorerGroup[];
}

function preserveRowOrder(rows: readonly QuestionBrowserSearchRow[]): QuestionBrowserSearchRow[] {
  return [...rows];
}

function choosePreviewQuestion(
  questions: readonly QuestionBrowserExplorerQuestion[],
): QuestionBrowserExplorerQuestion {
  return questions.find((question) => question.isActive) ?? questions[0];
}

export function buildQuestionBrowserExplorerState(
  rows: readonly QuestionBrowserSearchRow[],
  activeQuestionId: number | null,
): QuestionBrowserExplorerState {
  const grouped = new Map<number, QuestionBrowserExplorerQuestion[]>();

  for (const row of preserveRowOrder(rows)) {
    const questions = grouped.get(row.run_id) ?? [];
    questions.push({
      ...row,
      isActive: row.question_id === activeQuestionId,
    });
    grouped.set(row.run_id, questions);
  }

  return {
    groups: [...grouped.entries()].map(([runId, questions]) => {
      const previewQuestion = choosePreviewQuestion(questions);
      return {
        runId,
        runName: questions[0].run_name,
        matchCount: questions.length,
        previewQuestionId: previewQuestion.question_id,
        previewText: previewQuestion.prompt_preview,
        hasDegradedMatch: questions.some((question) => question.match_fidelity === 'degraded'),
        questions,
      };
    }),
  };
}

export function getDefaultExpandedRunIds(
  groups: readonly QuestionBrowserExplorerGroup[],
  activeQuestionId: number | null,
): number[] {
  if (activeQuestionId == null) {
    return [];
  }

  const activeGroup = groups.find((group) =>
    group.questions.some((question) => question.question_id === activeQuestionId),
  );
  return activeGroup ? [activeGroup.runId] : [];
}

export function getAdjacentQuestionId(
  rows: readonly QuestionBrowserSearchRow[],
  activeQuestionId: number | null,
  direction: -1 | 1,
): number | null {
  if (activeQuestionId == null) {
    return null;
  }

  const orderedRows = preserveRowOrder(rows);
  const activeIndex = orderedRows.findIndex((row) => row.question_id === activeQuestionId);
  if (activeIndex === -1) {
    return null;
  }

  const nextIndex = activeIndex + direction;
  if (nextIndex < 0 || nextIndex >= orderedRows.length) {
    return null;
  }

  return orderedRows[nextIndex].question_id;
}

export function summarizeGroupFidelity(groups: readonly QuestionBrowserExplorerGroup[]): QuestionBrowserMatchFidelity {
  return groups.some((group) => group.hasDegradedMatch) ? 'degraded' : 'full';
}
