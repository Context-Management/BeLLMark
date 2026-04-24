export interface CoverageSpecLike {
  version?: string;
  groups?: Array<{
    leaves?: unknown[];
  }>;
}

export interface CoverageSpecEnvelopeLike<T extends CoverageSpecLike = CoverageSpecLike> {
  spec?: T | null;
}

export type CoverageSpecInput<T extends CoverageSpecLike = CoverageSpecLike> =
  | T
  | CoverageSpecEnvelopeLike<T>
  | null
  | undefined;

function hasGroups<T extends CoverageSpecLike>(spec: CoverageSpecInput<T>): spec is T {
  return Boolean(spec && typeof spec === 'object' && 'groups' in spec && Array.isArray(spec.groups));
}

export function unwrapCoverageSpec<T extends CoverageSpecLike>(spec: CoverageSpecInput<T>): T | null {
  if (!spec) {
    return null;
  }
  if (hasGroups(spec)) {
    return spec;
  }
  if ('spec' in spec) {
    return unwrapCoverageSpec(spec.spec);
  }
  return null;
}

export function countCoverageLeaves(spec: CoverageSpecInput): number {
  const unwrapped = unwrapCoverageSpec(spec);
  if (!unwrapped?.groups) {
    return 0;
  }
  return unwrapped.groups.reduce((sum, group) => sum + (group.leaves?.length ?? 0), 0);
}

export function buildCoverageGenerationFields<T extends CoverageSpecLike>(
  coverageMode: string,
  coverageSpec: CoverageSpecInput<T>,
  coverageOutlineText: string,
): {
  coverage_mode: string;
  coverage_spec: T | null;
  coverage_outline_text: string | null;
} {
  const coverageEnabled = coverageMode !== 'none';
  return {
    coverage_mode: coverageMode,
    coverage_spec: coverageEnabled ? unwrapCoverageSpec(coverageSpec) : null,
    coverage_outline_text: coverageEnabled ? coverageOutlineText.trim() || null : null,
  };
}

export function strictCoverageFeasibilityMessage(
  requiredLeaves: number,
  selectedCount: number,
): string | null {
  if (selectedCount >= requiredLeaves) {
    return null;
  }
  return `Strict coverage requires at least ${requiredLeaves} questions. Current count is ${selectedCount}.`;
}
