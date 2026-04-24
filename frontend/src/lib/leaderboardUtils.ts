/**
 * Shared utilities for leaderboard grouping and model name normalization.
 * Used by Home.tsx (local card grouping) and EloLeaderboard.tsx (group-variants toggle).
 */

/**
 * Strip display-label decorations from a model name to get the canonical base name.
 *
 * Removed suffixes / sections:
 *  - Reasoning/Thinking annotations:  " [Reasoning (high)]", " [Reasoning]",
 *                                     " [Thinking]", " [Thinking (high)]"
 *  - Host suffix:            " (@ cachy)", " @ cachy"
 *  - Quantization in parens: " (Q4_K_M)", " (4bit)", " (MXFP4)"
 *  - Format in parens:       " (GGUF)", " (MLX)", " (GPTQ)", " (AWQ)"
 *  - Combined parens:        " (GGUF Q4_K_M @ cachy)"
 *  - Trailing clone-id:      " #125" (LM Studio preset duplicate marker)
 *
 * The result is trimmed.
 */
export function normalizeModelName(name: string): string {
  let n = name;

  // Remove [Reasoning] / [Thinking] with optional " (high|medium|low|...)" annotation.
  // Both Reasoning and Thinking can carry the parenthetical level — earlier versions
  // only allowed it on Reasoning, which left Gemini's "[Thinking (high)]" unmatched.
  n = n.replace(/\s*\[(?:Reasoning|Thinking)(?:\s*\([^)]*\))?\]/gi, '');

  // Remove parenthetical suffixes that contain format/quant/host info
  // e.g. "(GGUF Q4_K_M @ cachy)", "(@ cachy)", "(Q4_K_M)", "(MLX)"
  // These appear as trailing parenthetical groups
  n = n.replace(/\s*\([^)]*(?:@|GGUF|MLX|GPTQ|AWQ|Q[0-9]|[0-9]+bit|MXFP|fp[0-9])[^)]*\)/gi, '');

  // Remove trailing clone-id suffix (e.g. " #125") added when an LM Studio preset
  // is duplicated. Without this, "Foo #125" and "Foo #138" would never group.
  n = n.replace(/\s*#\d+\s*$/, '');

  return n.trim();
}

/**
 * A grouped leaderboard entry: the "best" entry (representative) plus all variants.
 */
export interface GroupedEntry<T> {
  /** The representative entry for the group (highest-ranked variant). */
  representative: T;
  /** All entries in this group, including the representative. */
  variants: T[];
  /** The normalized base name for this group. */
  baseName: string;
}

/**
 * Group a list of leaderboard entries by their normalized base model name.
 *
 * @param entries        The flat list of entries.
 * @param getName        Accessor for the display name of an entry.
 * @param getProvider    Accessor for the provider of an entry.
 * @param includeProvider  When true, provider is included in the grouping key so
 *                         same-named models from different providers stay separate.
 *                         Default: false (suitable for Home.tsx card view where
 *                         cloud vs local is already split).
 *
 * The first entry encountered in each group is used as the representative
 * (callers should pre-sort the input list in the desired ranking order so
 * the top-ranked variant becomes the representative).
 */
export function groupByBaseModel<T>(
  entries: T[],
  getName: (e: T) => string,
  getProvider: (e: T) => string,
  includeProvider = false,
): GroupedEntry<T>[] {
  const groups = new Map<string, GroupedEntry<T>>();

  for (const entry of entries) {
    const baseName = normalizeModelName(getName(entry));
    const provider = getProvider(entry);
    const key = includeProvider ? `${provider}::${baseName}` : baseName;

    const existing = groups.get(key);
    if (existing) {
      existing.variants.push(entry);
    } else {
      groups.set(key, {
        representative: entry,
        variants: [entry],
        baseName,
      });
    }
  }

  return [...groups.values()];
}
