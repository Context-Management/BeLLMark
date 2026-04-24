"""Coverage outline parsing and normalization helpers for suite generation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any


def _slug(value: str) -> str:
    value = re.sub(r"^[A-Za-z0-9]+\.\s*", "", value.strip())
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def _normalize_group_id(raw_id: str | None, label: str) -> str:
    if raw_id:
        return raw_id.strip().lower()
    return _slug(label)


def normalize_coverage_spec(data: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(data)
    groups = normalized.get("groups") or []
    if not groups:
        raise ValueError("coverage spec must contain groups")

    seen_group_ids: set[str] = set()
    seen_leaf_ids: set[str] = set()

    for group in groups:
        label = (group.get("label") or "").strip()
        if not label:
            raise ValueError("group label is required")

        group_id = _normalize_group_id(group.get("id"), label)
        if not group_id:
            raise ValueError("group id is required")
        if group_id in seen_group_ids:
            raise ValueError(f"duplicate group id: {group_id}")
        seen_group_ids.add(group_id)

        leaves = group.get("leaves") or []
        if not leaves:
            raise ValueError(f"group {group_id} must contain at least one leaves entry")

        normalized_leaves = []
        for leaf in leaves:
            leaf_label = (leaf.get("label") or "").strip()
            if not leaf_label:
                raise ValueError(f"leaf label is required for group {group_id}")
            leaf_id = (leaf.get("id") or f"{group_id}.{_slug(leaf_label)}").strip().lower()
            if not leaf_id:
                raise ValueError(f"leaf id is required for group {group_id}")
            if leaf_id in seen_leaf_ids:
                raise ValueError(f"duplicate leaf id: {leaf_id}")
            seen_leaf_ids.add(leaf_id)
            normalized_leaves.append({
                "id": leaf_id,
                "label": leaf_label,
                "description": leaf.get("description"),
                "aliases": list(leaf.get("aliases") or []),
            })

        group["id"] = group_id
        group["label"] = label
        group["leaves"] = normalized_leaves

    normalized["version"] = normalized.get("version") or "1"
    normalized["groups"] = groups
    return normalized


def parse_coverage_outline(outline: str) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None

    for raw_line in outline.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(r"^([A-Za-z0-9]+)\.\s+(.*)$", line)
        if heading_match:
            current_group = {
                "id": heading_match.group(1).strip().lower(),
                "label": heading_match.group(2).strip(),
                "leaves": [],
            }
            groups.append(current_group)
            continue

        if line.startswith("- "):
            if current_group is None:
                raise ValueError("leaf found before any group heading")
            leaf_label = line[2:].strip()
            current_group["leaves"].append({
                "label": leaf_label,
                "description": None,
                "aliases": [],
            })
            continue

        raise ValueError(f"unsupported outline line: {line}")

    return normalize_coverage_spec({"version": "1", "groups": groups})


def count_required_leaves(spec: dict[str, Any]) -> int:
    groups = spec.get("groups") or []
    return sum(len(group.get("leaves") or []) for group in groups)


def normalized_prompt_fingerprint(*parts: str) -> str:
    """Return a stable, coarse fingerprint for prompt dedupe checks."""
    text = " ".join(part for part in parts if part)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _trigrams(text: str) -> set[str]:
    normalized = normalized_prompt_fingerprint(text)
    if not normalized:
        return set()
    padded = f"  {normalized}  "
    return {padded[index : index + 3] for index in range(max(len(padded) - 2, 0))}


def trigram_jaccard(left: str, right: str) -> float:
    """Compute a character trigram Jaccard score for two prompts."""
    left_trigrams = _trigrams(left)
    right_trigrams = _trigrams(right)
    if not left_trigrams and not right_trigrams:
        return 1.0
    if not left_trigrams or not right_trigrams:
        return 0.0
    return len(left_trigrams & right_trigrams) / len(left_trigrams | right_trigrams)


def find_candidate_duplicate_pairs(
    questions: list[dict[str, Any]],
    *,
    threshold: float = 0.72,
) -> list[tuple[int, int]]:
    """Return question index pairs that are plausible duplicates."""
    pairs: list[tuple[int, int]] = []
    fingerprints: list[str] = []
    prompt_texts: list[str] = []

    for question in questions:
        prompt_text = " ".join([
            question.get("system_prompt") or "",
            question.get("user_prompt") or "",
        ]).strip()
        prompt_texts.append(prompt_text)
        fingerprints.append(normalized_prompt_fingerprint(prompt_text))

    for left_index in range(len(questions)):
        for right_index in range(left_index + 1, len(questions)):
            if fingerprints[left_index] == fingerprints[right_index]:
                pairs.append((left_index, right_index))
                continue
            if trigram_jaccard(prompt_texts[left_index], prompt_texts[right_index]) >= threshold:
                pairs.append((left_index, right_index))

    return pairs


def cluster_duplicate_pairs(pairs: list[tuple[int, int]]) -> list[list[int]]:
    """Cluster pairwise duplicate links into connected components."""
    if not pairs:
        return []

    adjacency: dict[int, set[int]] = {}
    for left, right in pairs:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    clusters: list[list[int]] = []
    visited: set[int] = set()

    for node in sorted(adjacency):
        if node in visited:
            continue
        stack = [node]
        cluster: list[int] = []
        visited.add(node)
        while stack:
            current = stack.pop()
            cluster.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        clusters.append(sorted(cluster))

    return clusters


@dataclass(frozen=True)
class CoverageLeaf:
    id: str
    label: str
    group_id: str
    group_label: str


@dataclass(frozen=True)
class GenerationSlot:
    slot_index: int
    required_leaf_ids: list[str]
    required_leaf_labels: list[str]


@dataclass(frozen=True)
class CoveragePlan:
    mode: str
    leaves: list[CoverageLeaf]
    slots: list[GenerationSlot]


def flatten_leaves(spec: dict[str, Any]) -> list[CoverageLeaf]:
    leaves: list[CoverageLeaf] = []
    for group in spec.get("groups") or []:
        group_id = group["id"]
        group_label = group["label"]
        for leaf in group.get("leaves") or []:
            leaves.append(CoverageLeaf(
                id=leaf["id"],
                label=leaf["label"],
                group_id=group_id,
                group_label=group_label,
            ))
    return leaves


def build_coverage_plan(
    spec: dict[str, Any],
    *,
    count: int,
    mode: str,
    max_topics_per_question: int,
) -> CoveragePlan:
    leaves = flatten_leaves(spec)
    slots: list[GenerationSlot] = []

    if mode == "strict_leaf_coverage":
        if not leaves:
            return CoveragePlan(mode=mode, leaves=leaves, slots=slots)
        for index in range(count):
            leaf = leaves[index % len(leaves)]
            slots.append(GenerationSlot(
                slot_index=index,
                required_leaf_ids=[leaf.id],
                required_leaf_labels=[leaf.label],
            ))
        return CoveragePlan(mode=mode, leaves=leaves, slots=slots)

    if mode == "compact_leaf_coverage":
        current_group_id: str | None = None
        current_ids: list[str] = []
        current_labels: list[str] = []

        def flush_slot() -> None:
            if current_ids:
                slots.append(GenerationSlot(
                    slot_index=len(slots),
                    required_leaf_ids=list(current_ids),
                    required_leaf_labels=list(current_labels),
                ))

        for leaf in leaves:
            group_changed = current_group_id is not None and leaf.group_id != current_group_id
            capacity_reached = len(current_ids) >= max_topics_per_question
            if current_ids and (group_changed or capacity_reached):
                flush_slot()
                current_ids.clear()
                current_labels.clear()

            current_group_id = leaf.group_id
            current_ids.append(leaf.id)
            current_labels.append(leaf.label)

        flush_slot()
        return CoveragePlan(mode=mode, leaves=leaves, slots=slots)

    raise ValueError(f"unsupported coverage mode: {mode}")
