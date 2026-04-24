"""Autonomous suite refinement loop for overnight benchmark optimization."""

from __future__ import annotations

import asyncio
import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.orm import Session

from app.core.generators import generate, resolve_temperature
from app.core.runner import BenchmarkRunner
from app.db.models import (
    BenchmarkRun,
    JudgeMode,
    Judgment,
    ModelPreset,
    PromptSuite,
    PromptSuiteItem,
    Question,
    RunStatus,
    TaskStatus,
    TemperatureMode,
)


@dataclass
class SuiteAutoresearchConfig:
    suite_id: int | None
    subject_model_ids: list[int]
    judge_model_ids: list[int]
    editor_model_id: int
    max_iterations: int = 12
    output_dir: Path = Path("results/autoresearch/latest")
    dry_run: bool = False
    quality_margin: float = 0.02
    benchmark_name_prefix: str = "[autoresearch]"
    temperature_mode: TemperatureMode = TemperatureMode.provider_default


@dataclass
class QuestionEvaluation:
    quality: float
    discrimination: float
    stability: float
    judge_agreement: float
    winner_entropy: float
    sample_count: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentDecision:
    action: str
    quality_delta: float
    rationale: str


@dataclass
class QuestionRanking:
    question_order: int
    weakness_score: float
    quality: float
    discrimination: float
    stability: float
    judge_agreement: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteBaselineSummary:
    suite_id: int
    suite_name: str
    question_count: int
    completed_run_count: int
    question_rankings: list[QuestionRanking]


@dataclass
class ArtifactPaths:
    root_dir: Path
    start_dir: Path
    work_dir: Path
    result_dir: Path


@dataclass
class SuiteAutoresearchResult:
    suite_id: int
    iterations_completed: int
    final_suite_path: Path
    artifact_root: Path


def decide_experiment(incumbent: QuestionEvaluation, candidate: QuestionEvaluation, margin: float = 0.02) -> ExperimentDecision:
    quality_delta = round(candidate.quality - incumbent.quality, 4)
    if quality_delta > margin:
        return ExperimentDecision(
            action="keep",
            quality_delta=quality_delta,
            rationale="candidate improved overall quality above the acceptance margin",
        )
    return ExperimentDecision(
        action="revert",
        quality_delta=quality_delta,
        rationale="candidate did not clear the quality acceptance margin",
    )


class SuiteAutoresearchService:
    def __init__(self, session: Session, config: SuiteAutoresearchConfig):
        self.session = session
        self.config = config
        self._artifacts: ArtifactPaths | None = None
        self._baseline_summary: SuiteBaselineSummary | None = None

    def select_baseline_suite_id(self) -> int:
        rows = (
            self.session.query(
                BenchmarkRun.source_suite_id,
            )
            .filter(
                BenchmarkRun.source_suite_id.isnot(None),
                BenchmarkRun.status == RunStatus.completed,
            )
            .all()
        )
        counts: dict[int, int] = {}
        for (suite_id,) in rows:
            counts[suite_id] = counts.get(suite_id, 0) + 1
        if not counts:
            raise ValueError("No completed benchmark runs with source_suite_id found")
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def build_suite_baseline(self, suite_id: int) -> SuiteBaselineSummary:
        suite = self.session.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
        if suite is None:
            raise ValueError(f"Suite {suite_id} not found")

        runs = (
            self.session.query(BenchmarkRun)
            .filter(
                BenchmarkRun.source_suite_id == suite_id,
                BenchmarkRun.status == RunStatus.completed,
            )
            .all()
        )
        by_order: dict[int, list[QuestionEvaluation]] = {item.order: [] for item in suite.items}

        for run in runs:
            criteria = run.criteria or suite.default_criteria or []
            questions = (
                self.session.query(Question)
                .filter(Question.benchmark_id == run.id)
                .order_by(Question.order)
                .all()
            )
            for question in questions:
                if question.order in by_order:
                    by_order[question.order].append(self._evaluate_question(question, criteria))

        rankings: list[QuestionRanking] = []
        for item in suite.items:
            evaluations = by_order.get(item.order, [])
            if evaluations:
                quality = mean(ev.quality for ev in evaluations)
                discrimination = mean(ev.discrimination for ev in evaluations)
                stability = mean(ev.stability for ev in evaluations)
                judge_agreement = mean(ev.judge_agreement for ev in evaluations)
            else:
                quality = discrimination = stability = judge_agreement = 0.0
            weakness_score = round(1.0 - quality, 4)
            rankings.append(
                QuestionRanking(
                    question_order=item.order,
                    weakness_score=weakness_score,
                    quality=round(quality, 4),
                    discrimination=round(discrimination, 4),
                    stability=round(stability, 4),
                    judge_agreement=round(judge_agreement, 4),
                    evidence={"historical_samples": len(evaluations)},
                )
            )

        rankings.sort(key=lambda item: (-item.weakness_score, item.question_order))
        summary = SuiteBaselineSummary(
            suite_id=suite.id,
            suite_name=suite.name,
            question_count=len(suite.items),
            completed_run_count=len(runs),
            question_rankings=rankings,
        )
        self._baseline_summary = summary
        return summary

    def initialize_artifacts(self, suite_id: int) -> ArtifactPaths:
        summary = self._baseline_summary or self.build_suite_baseline(suite_id)
        suite = self.session.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
        if suite is None:
            raise ValueError(f"Suite {suite_id} not found")

        root_dir = Path(self.config.output_dir)
        start_dir = root_dir / "start"
        work_dir = root_dir / "work"
        result_dir = root_dir / "result"
        kept_dir = work_dir / "kept"
        reverted_dir = work_dir / "reverted"
        for path in (start_dir, work_dir, result_dir, kept_dir, reverted_dir):
            path.mkdir(parents=True, exist_ok=True)

        (start_dir / "baseline-suite.json").write_text(json.dumps(self._suite_payload(suite, suite.items), indent=2))
        (start_dir / "baseline-summary.json").write_text(
            json.dumps(
                {
                    "suite_id": summary.suite_id,
                    "suite_name": summary.suite_name,
                    "question_count": summary.question_count,
                    "completed_run_count": summary.completed_run_count,
                    "question_rankings": [asdict(item) for item in summary.question_rankings],
                },
                indent=2,
            )
        )
        with (work_dir / "experiments.tsv").open("w", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(
                [
                    "iteration",
                    "question_order",
                    "change_type",
                    "decision",
                    "quality_delta",
                    "incumbent_quality",
                    "candidate_quality",
                    "change_description",
                ]
            )

        self._artifacts = ArtifactPaths(root_dir=root_dir, start_dir=start_dir, work_dir=work_dir, result_dir=result_dir)
        return self._artifacts

    async def run(self) -> SuiteAutoresearchResult:
        suite_id = self.config.suite_id or self.select_baseline_suite_id()
        summary = self.build_suite_baseline(suite_id)
        artifacts = self.initialize_artifacts(suite_id)
        suite = self.session.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
        if suite is None:
            raise ValueError(f"Suite {suite_id} not found")

        working_items = [self._item_payload(item) for item in sorted(suite.items, key=lambda item: item.order)]
        rankings = summary.question_rankings or []

        iterations_completed = 0
        for iteration in range(self.config.max_iterations):
            if not rankings:
                break
            target = rankings[iteration % len(rankings)]
            incumbent = next((item for item in working_items if item["order"] == target.question_order), None)
            if incumbent is None:
                continue

            candidate_change = await self._propose_candidate_change(incumbent, summary, iteration)
            incumbent_eval, candidate_eval = await self._evaluate_experiment(incumbent, candidate_change, iteration)
            decision = decide_experiment(incumbent_eval, candidate_eval, margin=self.config.quality_margin)
            self._record_experiment(iteration, target.question_order, candidate_change, incumbent_eval, candidate_eval, decision)

            if decision.action == "keep":
                replacement = self._merge_item_change(incumbent, candidate_change)
                for idx, item in enumerate(working_items):
                    if item["order"] == target.question_order:
                        working_items[idx] = replacement
                        break

            iterations_completed += 1

        final_payload = self._suite_payload(suite, working_items)
        final_suite_path = artifacts.result_dir / "final-suite.json"
        final_suite_path.write_text(json.dumps(final_payload, indent=2))
        (artifacts.result_dir / "final-report.md").write_text(self._final_report(summary, iterations_completed, final_payload))

        return SuiteAutoresearchResult(
            suite_id=suite_id,
            iterations_completed=iterations_completed,
            final_suite_path=final_suite_path,
            artifact_root=artifacts.root_dir,
        )

    async def _propose_candidate_change(self, incumbent: dict[str, Any], summary: SuiteBaselineSummary, iteration: int) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "change_type": "refine",
                "change_description": "dry-run placeholder candidate",
                "question": {
                    "system_prompt": incumbent["system_prompt"],
                    "user_prompt": incumbent["user_prompt"],
                    "expected_answer": incumbent.get("expected_answer"),
                },
            }

        editor = self.session.query(ModelPreset).filter(ModelPreset.id == self.config.editor_model_id).first()
        if editor is None:
            raise ValueError(f"Editor model {self.config.editor_model_id} not found")

        system_prompt = (
            "You improve benchmark questions for LLM evaluation. "
            "Return strict JSON with keys: change_type, change_description, question."
        )
        user_prompt = json.dumps(
            {
                "suite_name": summary.suite_name,
                "iteration": iteration + 1,
                "target_question": incumbent,
                "goal": "Improve discrimination, stability, and rubric clarity without drifting off-topic.",
            },
            indent=2,
        )
        temperature = resolve_temperature(editor, self.config.temperature_mode, 0.7)
        response = await generate(editor, system_prompt, user_prompt, json_mode=True, temperature=temperature)
        if not response.get("success"):
            raise RuntimeError(response.get("error") or "candidate generation failed")
        payload = self._extract_json(response.get("content") or response.get("full_content") or "")
        if not isinstance(payload, dict) or "question" not in payload:
            raise ValueError("Candidate generation did not return the expected JSON object")
        return payload

    async def _evaluate_experiment(
        self,
        incumbent: dict[str, Any],
        candidate_change: dict[str, Any],
        iteration: int,
    ) -> tuple[QuestionEvaluation, QuestionEvaluation]:
        incumbent_eval = QuestionEvaluation(
            quality=0.0,
            discrimination=0.0,
            stability=0.0,
            judge_agreement=0.0,
            winner_entropy=1.0,
            sample_count=0,
            details={"mode": "dry-run"},
        )
        candidate_eval = incumbent_eval
        if self.config.dry_run:
            return incumbent_eval, candidate_eval

        suite = self.session.query(PromptSuite).filter(PromptSuite.id == (self.config.suite_id or self.select_baseline_suite_id())).first()
        if suite is None:
            raise ValueError("Unable to load suite for experiment evaluation")

        run = BenchmarkRun(
            name=f"{self.config.benchmark_name_prefix} iter {iteration + 1} q{incumbent['order']}",
            status=RunStatus.pending,
            judge_mode=JudgeMode.comparison,
            criteria=suite.default_criteria or [],
            model_ids=list(self.config.subject_model_ids),
            judge_ids=list(self.config.judge_model_ids),
            temperature_mode=self.config.temperature_mode,
        )
        self.session.add(run)
        self.session.flush()

        candidate_item = self._merge_item_change(incumbent, candidate_change)
        for order, item in enumerate((incumbent, candidate_item)):
            self.session.add(
                Question(
                    benchmark_id=run.id,
                    order=order,
                    system_prompt=item["system_prompt"],
                    user_prompt=item["user_prompt"],
                    expected_answer=item.get("expected_answer"),
                )
            )
        self.session.commit()

        runner = BenchmarkRunner(self.session, run.id)
        await runner.run()
        self.session.expire_all()

        questions = (
            self.session.query(Question)
            .filter(Question.benchmark_id == run.id)
            .order_by(Question.order)
            .all()
        )
        incumbent_eval = self._evaluate_question(questions[0], run.criteria or [])
        candidate_eval = self._evaluate_question(questions[1], run.criteria or [])
        return incumbent_eval, candidate_eval

    def _evaluate_question(self, question: Question, criteria: list[dict[str, Any]]) -> QuestionEvaluation:
        judgments = (
            self.session.query(Judgment)
            .filter(
                Judgment.question_id == question.id,
                Judgment.status == TaskStatus.success,
            )
            .all()
        )
        if not judgments:
            return QuestionEvaluation(
                quality=0.0,
                discrimination=0.0,
                stability=0.0,
                judge_agreement=0.0,
                winner_entropy=1.0,
                sample_count=0,
                details={},
            )

        weight_map = {criterion["name"]: criterion.get("weight", 1.0) for criterion in criteria}
        total_weight = sum(weight_map.values()) or 1.0

        judge_model_scores: list[dict[int, float]] = []
        winners: list[int] = []

        for judgment in judgments:
            model_scores: dict[int, float] = {}
            if judgment.scores:
                for mid_raw, criterion_scores in judgment.scores.items():
                    model_id = int(mid_raw)
                    if isinstance(criterion_scores, dict):
                        weighted_sum = 0.0
                        for criterion_name, value in criterion_scores.items():
                            weighted_sum += float(value) * weight_map.get(criterion_name, 1.0)
                        model_scores[model_id] = weighted_sum / total_weight
                    else:
                        model_scores[model_id] = float(criterion_scores)
            elif judgment.rankings and judgment.blind_mapping:
                scale = max(len(judgment.rankings), 1)
                for idx, label in enumerate(judgment.rankings):
                    blind_id = judgment.blind_mapping.get(label)
                    if blind_id is not None:
                        model_scores[int(blind_id)] = 10.0 * (scale - idx) / scale

            if not model_scores:
                continue
            judge_model_scores.append(model_scores)
            winners.append(max(model_scores.items(), key=lambda item: item[1])[0])

        if not judge_model_scores:
            return QuestionEvaluation(
                quality=0.0,
                discrimination=0.0,
                stability=0.0,
                judge_agreement=0.0,
                winner_entropy=1.0,
                sample_count=0,
                details={},
            )

        discrimination = mean(
            max(scores.values()) - min(scores.values()) for scores in judge_model_scores
        ) / 10.0

        modal_count = max(winners.count(winner_id) for winner_id in set(winners))
        judge_agreement = modal_count / len(winners)

        per_model_stds: list[float] = []
        all_model_ids = sorted({model_id for scores in judge_model_scores for model_id in scores})
        for model_id in all_model_ids:
            values = [scores[model_id] for scores in judge_model_scores if model_id in scores]
            if len(values) >= 2:
                per_model_stds.append(pstdev(values))
        stability = max(0.0, 1.0 - ((mean(per_model_stds) / 10.0) if per_model_stds else 0.0))

        winner_entropy = self._normalized_entropy(winners)
        quality = (0.5 * discrimination) + (0.3 * judge_agreement) + (0.2 * stability)

        return QuestionEvaluation(
            quality=round(quality, 4),
            discrimination=round(discrimination, 4),
            stability=round(stability, 4),
            judge_agreement=round(judge_agreement, 4),
            winner_entropy=round(winner_entropy, 4),
            sample_count=len(judge_model_scores),
            details={"winner_ids": winners},
        )

    def _normalized_entropy(self, winners: list[int]) -> float:
        if len(winners) <= 1:
            return 0.0
        counts = [winners.count(winner_id) / len(winners) for winner_id in set(winners)]
        entropy = -sum(prob * math.log(prob, 2) for prob in counts if prob > 0)
        max_entropy = math.log(len(counts), 2) if len(counts) > 1 else 1.0
        return 0.0 if max_entropy == 0 else entropy / max_entropy

    def _suite_payload(self, suite: PromptSuite, items: list[Any]) -> dict[str, Any]:
        serialized_items = []
        for item in items:
            if isinstance(item, PromptSuiteItem):
                serialized_items.append(self._item_payload(item))
            else:
                serialized_items.append(dict(item))
        return {
            "suite_id": suite.id,
            "name": suite.name,
            "description": suite.description,
            "default_criteria": suite.default_criteria,
            "item_count": len(serialized_items),
            "items": sorted(serialized_items, key=lambda item: item["order"]),
        }

    def _item_payload(self, item: PromptSuiteItem) -> dict[str, Any]:
        return {
            "order": item.order,
            "system_prompt": item.system_prompt,
            "user_prompt": item.user_prompt,
            "expected_answer": item.expected_answer,
            "category": item.category,
            "difficulty": item.difficulty,
            "criteria": item.criteria,
        }

    def _merge_item_change(self, incumbent: dict[str, Any], candidate_change: dict[str, Any]) -> dict[str, Any]:
        payload = dict(incumbent)
        candidate_question = self._normalize_candidate_question(candidate_change.get("question", {}))
        payload.update(
            {
                "system_prompt": candidate_question.get("system_prompt", incumbent["system_prompt"]),
                "user_prompt": candidate_question.get("user_prompt", incumbent["user_prompt"]),
                "expected_answer": candidate_question.get("expected_answer", incumbent.get("expected_answer")),
            }
        )
        return payload

    def _normalize_candidate_question(self, raw_question: Any) -> dict[str, Any]:
        if isinstance(raw_question, dict):
            return raw_question
        if isinstance(raw_question, str):
            stripped = raw_question.strip()
            if not stripped:
                return {}
            try:
                parsed = self._extract_json(stripped)
            except Exception:
                return {"user_prompt": stripped}
            return parsed if isinstance(parsed, dict) else {"user_prompt": stripped}
        return {}

    def _record_experiment(
        self,
        iteration: int,
        question_order: int,
        candidate_change: dict[str, Any],
        incumbent_eval: QuestionEvaluation,
        candidate_eval: QuestionEvaluation,
        decision: ExperimentDecision,
    ) -> None:
        if self._artifacts is None:
            return
        experiments_path = self._artifacts.work_dir / "experiments.tsv"
        with experiments_path.open("a", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(
                [
                    iteration + 1,
                    question_order,
                    candidate_change.get("change_type", "refine"),
                    decision.action,
                    decision.quality_delta,
                    incumbent_eval.quality,
                    candidate_eval.quality,
                    candidate_change.get("change_description", ""),
                ]
            )

        bucket = "kept" if decision.action == "keep" else "reverted"
        detail_path = self._artifacts.work_dir / bucket / f"iteration-{iteration + 1:03d}.json"
        detail_path.write_text(
            json.dumps(
                {
                    "iteration": iteration + 1,
                    "question_order": question_order,
                    "candidate_change": candidate_change,
                    "incumbent": asdict(incumbent_eval),
                    "candidate": asdict(candidate_eval),
                    "decision": asdict(decision),
                },
                indent=2,
            )
        )

    def _final_report(self, summary: SuiteBaselineSummary, iterations_completed: int, final_payload: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"# Suite Autoresearch Result",
                "",
                f"- Baseline suite: `{summary.suite_name}` (`{summary.suite_id}`)",
                f"- Historical completed runs: `{summary.completed_run_count}`",
                f"- Iterations completed: `{iterations_completed}`",
                f"- Final question count: `{final_payload['item_count']}`",
            ]
        )

    def _extract_json(self, text: str) -> Any:
        text = text.strip()
        if not text:
            raise ValueError("Empty model response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
            if not match:
                raise
            return json.loads(match.group(1))
