import { useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export type SectionId =
  | 'overview'
  | 'charts'
  | 'scores'
  | 'statistics'
  | 'judges'
  | 'best-answers'
  | 'worst-answers'
  | 'judge-disagreement'
  | 'compare-parent'
  | `model-${string}`
  | `question-${string}`;

const STATIC_SECTIONS: ReadonlySet<string> = new Set([
  'overview',
  'charts',
  'scores',
  'statistics',
  'judges',
  'best-answers',
  'worst-answers',
  'judge-disagreement',
  'compare-parent',
]);

function isValidSectionId(hash: string): hash is SectionId {
  if (STATIC_SECTIONS.has(hash)) return true;
  if (/^model-.+$/.test(hash)) return true;
  if (/^question-.+$/.test(hash)) return true;
  return false;
}

function parseSectionFromHash(locationHash: string): SectionId {
  // location.hash starts with '#', strip it
  const raw = locationHash.startsWith('#') ? locationHash.slice(1) : locationHash;
  if (isValidSectionId(raw)) return raw;
  return 'overview';
}

export interface UseResultsNavReturn {
  section: SectionId;
  navigate: (section: SectionId) => void;
}

export function useResultsNav(): UseResultsNavReturn {
  const location = useLocation();
  const routerNavigate = useNavigate();

  // Derive section directly from hash — no effect needed
  const section = useMemo(
    () => parseSectionFromHash(location.hash),
    [location.hash]
  );

  const navigate = useCallback(
    (nextSection: SectionId) => {
      routerNavigate({ hash: nextSection }, { replace: false });
    },
    [routerNavigate]
  );

  return { section, navigate };
}
