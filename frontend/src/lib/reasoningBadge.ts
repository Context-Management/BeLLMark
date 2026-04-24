type ReasoningBadgeInput = {
  is_reasoning?: boolean;
  reasoning_level?: string | null;
};

export function getReasoningBadgeLabel(model: ReasoningBadgeInput): string | null {
  if (!model.is_reasoning) return null;
  return model.reasoning_level || 'on';
}
