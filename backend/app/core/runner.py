"""
Benchmark Runner - Main orchestration for running benchmarks.

Handles:
- Parallel generation across models
- Smart retry logic with exponential backoff
- Progress tracking via WebSocket
- Graceful cancellation
"""

import asyncio
import logging
import random as random_module
import socket
import copy

logger = logging.getLogger(__name__)
from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone, timedelta

from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment, ModelPreset,
    RunStatus, TaskStatus, JudgeMode, QuestionAttachment, Attachment, TemperatureMode, ProviderType
)
from app.core.discovery import discover_lmstudio
from app.core.generators import generate, resolve_temperature, ensure_lmstudio_model, sync_lmstudio_preset_metadata
from app.core.judges import judge_comparison, judge_separate, summarize_judge_comments
from app.core.display_labels import resolve_display_labels
from app.ws.progress import manager

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds
SWEEP_DELAYS = [30, 60, 120]  # seconds between retry sweeps for still-failed judgments
# Per-attempt API-call ceiling. The timer starts ONLY when the semaphore is
# acquired and the actual API call fires — queue wait time does NOT count
# against this budget. With MAX_RETRIES=3, worst-case API time per judgment
# is 3 * 600s = 1800s, plus 17s of backoff sleeps. A judgment can legitimately
# sit in the provider queue for longer than this if Anthropic/LM Studio is
# saturated — smart retry gets its full budget regardless of queue depth.
PER_ATTEMPT_TIMEOUT = 600  # 10 min per judge API call attempt
# Generation ceiling is wider — real reasoning-high Opus calls have been
# observed at 3227s on complex prompts. Set at 1 hour to cover the observed
# tail + margin, but still catch infinite hangs (httpx's per-chunk read
# timeout does NOT fire on slow-drip responses from providers like OpenRouter
# where a keepalive byte every few minutes resets the read clock). Without
# this outer wall-clock cap, a stuck generation blocks its model's entire
# queue forever.
PER_ATTEMPT_GEN_TIMEOUT = 3600  # 60 min per generation API call attempt

# Cache resolved IPs so we don't hit DNS on every model
_resolved_ip_cache: Dict[str, str] = {}


async def _resolve_lmstudio_server_key(base_url: str) -> str:
    """Resolve an LM Studio base_url to a canonical server key using IP address.

    This ensures that mini.local:1234 and 192.168.0.112:1234 map to the
    same server key, preventing parallel model loads on the same server.
    """
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    hostname = parsed.hostname or parsed.netloc
    port = parsed.port or 1234

    cache_key = f"{hostname}:{port}"
    if cache_key not in _resolved_ip_cache:
        try:
            loop = asyncio.get_event_loop()
            infos = await loop.getaddrinfo(hostname, port, family=socket.AF_INET)
            ip = infos[0][4][0] if infos else hostname
            _resolved_ip_cache[cache_key] = f"lmstudio_{ip}:{port}"
        except (socket.gaierror, OSError):
            _resolved_ip_cache[cache_key] = f"lmstudio_{cache_key}"
    return _resolved_ip_cache[cache_key]


class BenchmarkRunner:
    """Orchestrates a complete benchmark run with parallel generation and judging."""

    def __init__(self, db: Session, run_id: int):
        self.db = db
        self.run_id = run_id
        self.benchmark_run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        self.cancelled = False
        self._provider_semaphores: Dict[str, asyncio.Semaphore] = {}

    def cancel(self):
        """Mark this runner as cancelled."""
        self.cancelled = True

    async def _watchdog(self, stale_threshold_seconds: int = 1860):
        """Detect and mark stale running generations as failed.

        Runs as a background task during the generation phase. Checks every 60s
        for generations stuck in 'running' longer than the threshold (default 1860s,
        just above the 1800s LM Studio httpx timeout). Marked-failed generations
        are picked up by the existing _retry_failed_generations() checkpoint.
        """
        from app.db.database import SessionLocal
        while not self.cancelled:
            await asyncio.sleep(60)
            if self.cancelled:
                break
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold_seconds)
            db = SessionLocal()
            try:
                stale = db.query(Generation).join(Question).filter(
                    Question.benchmark_id == self.run_id,
                    Generation.status == TaskStatus.running,
                    Generation.started_at.isnot(None),
                    Generation.started_at < cutoff
                ).all()
                for gen in stale:
                    logger.warning(
                        f"Watchdog: generation {gen.id} stuck for >{stale_threshold_seconds}s, marking failed"
                    )
                    gen.status = TaskStatus.failed
                    gen.error = f"Watchdog: timed out after {stale_threshold_seconds}s"
                    gen.completed_at = datetime.now(timezone.utc)
                if stale:
                    db.commit()
            except Exception as e:
                logger.warning(f"Watchdog check failed: {e}")
            finally:
                db.close()

    async def _judgment_watchdog(self, stale_threshold_seconds: int = 960):
        """Detect and mark stale running judgments as failed.

        Mirrors the generation watchdog — runs as a background task during the
        judging phase. Tracks when each judgment first entered 'running' and
        marks it failed if it exceeds the threshold. Marked-failed judgments
        are picked up by _retry_failed_judgments().
        """
        from app.db.database import SessionLocal
        # Track first-seen timestamps for running judgments
        running_since: Dict[int, datetime] = {}
        while not self.cancelled:
            await asyncio.sleep(60)
            if self.cancelled:
                break
            now = datetime.now(timezone.utc)
            db = SessionLocal()
            try:
                running = db.query(Judgment).join(Question).filter(
                    Question.benchmark_id == self.run_id,
                    Judgment.status == TaskStatus.running,
                ).all()
                current_running_ids = set()
                for j in running:
                    current_running_ids.add(j.id)
                    if j.id not in running_since:
                        running_since[j.id] = now
                    elif (now - running_since[j.id]).total_seconds() > stale_threshold_seconds:
                        logger.warning(
                            f"Judgment watchdog: judgment {j.id} stuck for >{stale_threshold_seconds}s, marking failed"
                        )
                        j.status = TaskStatus.failed
                        j.error = f"Watchdog: timed out after {stale_threshold_seconds}s"
                        j.completed_at = now
                        del running_since[j.id]
                # Clean up tracking for judgments no longer running
                running_since = {k: v for k, v in running_since.items() if k in current_running_ids}
                db.commit()
            except Exception as e:
                logger.warning(f"Judgment watchdog check failed: {e}")
            finally:
                db.close()

    def _update_elo_on_completion(self):
        """Update ELO ratings after successful benchmark completion.

        Spin-offs (parent_run_id IS NOT NULL) are excluded: re-judging the same
        generations with different criteria must not affect global ELO rankings.
        """
        if self.benchmark_run and self.benchmark_run.parent_run_id is not None:
            logger.info(
                f"Run {self.run_id}: skipping ELO update (spin-off of run {self.benchmark_run.parent_run_id})"
            )
            return
        from app.core.elo_service import update_elo_ratings_for_run
        try:
            update_elo_ratings_for_run(self.db, self.run_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"ELO update failed: {e}")

        # A non-spin-off run has just transitioned to `completed`, which
        # changes the inputs to the aggregate leaderboard. Invalidate the
        # cache so the next request recomputes.
        from app.api.elo import invalidate_aggregate_leaderboard_cache
        invalidate_aggregate_leaderboard_cache()

    def _mark_judgment_failed(self, judgment_id: int, error: str):
        """Mark a judgment as failed using a fresh DB session."""
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
            if judgment and judgment.status not in (TaskStatus.success, TaskStatus.failed):
                judgment.status = TaskStatus.failed
                judgment.error = error
                judgment.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    async def _get_semaphore(self, preset: "ModelPreset") -> asyncio.Semaphore:
        """Get or create the concurrency semaphore for a preset's provider/server."""
        from app.core.concurrency import (
            resolve_concurrency_key_async,
            get_effective_concurrency,
            LOCAL_PROVIDERS,
        )
        provider_str = preset.provider.value if hasattr(preset.provider, 'value') else str(preset.provider)

        if provider_str in LOCAL_PROVIDERS and preset.base_url:
            _, server_key = await resolve_concurrency_key_async(provider_str, preset.base_url)
            sem_key = f"{provider_str}:{server_key}"
        else:
            sem_key = provider_str
            server_key = None

        if sem_key not in self._provider_semaphores:
            if self.benchmark_run and self.benchmark_run.sequential_mode:
                limit = 1
            else:
                limit = get_effective_concurrency(self.db, provider_str, server_key)
            self._provider_semaphores[sem_key] = asyncio.Semaphore(limit)
            print(f"[Run {self.run_id}] Concurrency for {sem_key}: {limit}")

        return self._provider_semaphores[sem_key]

    async def _throttled_generate(self, preset, *args, **kwargs):
        """Throttled wrapper for generate() with per-provider semaphore."""
        sem = await self._get_semaphore(preset)
        async with sem:
            return await generate(preset, *args, **kwargs)

    async def _throttled_judge_comparison(self, preset, *args, **kwargs):
        """Throttled wrapper for judge_comparison() with per-provider semaphore."""
        sem = await self._get_semaphore(preset)
        async with sem:
            return await judge_comparison(preset, *args, **kwargs)

    async def _throttled_judge_separate(self, preset, *args, **kwargs):
        """Throttled wrapper for judge_separate() with per-provider semaphore."""
        sem = await self._get_semaphore(preset)
        async with sem:
            return await judge_separate(preset, *args, **kwargs)

    def _label(self, preset) -> str:
        """Get resolved display label for a preset (falls back to preset.name)."""
        return getattr(self, '_resolved_labels', {}).get(preset.id, preset.name)

    async def _reconcile_lmstudio_snapshot_variants(
        self,
        questions: list[Question],
        model_presets: Dict[int, ModelPreset],
    ) -> None:
        """Repair stale LM Studio presets in active runs using the run snapshot.

        If a run snapshot says a preset was intended to be a specific quant/format
        variant, and the live LM Studio discovery returns a unique canonical model
        for that variant, retarget the preset and invalidate generations that were
        produced by the wrong resolved model_version.
        """
        snapshot = self.benchmark_run.run_config_snapshot or {}
        snapshot_models = {
            model.get("id"): model
            for model in snapshot.get("models", [])
            if isinstance(model, dict) and model.get("id") is not None
        }
        if not snapshot_models:
            return

        discovery_cache: Dict[str, list[dict]] = {}
        question_ids = [question.id for question in questions]
        snapshot_changed = False
        affected_question_ids: set[int] = set()

        for preset_id, preset in model_presets.items():
            if preset.provider != ProviderType.lmstudio:
                continue

            snapshot_model = snapshot_models.get(preset_id)
            if not snapshot_model:
                continue

            target_quant = snapshot_model.get("quantization")
            target_format = (snapshot_model.get("model_format") or "").upper()
            target_name = snapshot_model.get("name")
            target_base_url = snapshot_model.get("base_url") or preset.base_url
            if not target_quant or not target_format or not target_name:
                continue

            if target_base_url not in discovery_cache:
                try:
                    discovery_cache[target_base_url] = await discover_lmstudio(target_base_url)
                except Exception as exc:
                    logger.warning(
                        "Run %s: LM Studio discovery failed for %s (%s) — skipping snapshot reconciliation for this host; affected generations will fail individually with their own retry budget.",
                        self.run_id,
                        target_base_url,
                        exc,
                    )
                    discovery_cache[target_base_url] = []

            candidates = [
                model for model in discovery_cache[target_base_url]
                if model.get("name") == target_name
                and model.get("quantization") == target_quant
                and (model.get("model_format") or "").upper() == target_format
            ]
            if len(candidates) != 1:
                continue

            target = candidates[0]
            target_model_id = target["model_id"]
            target_raw_format = "safetensors" if target_format == "MLX" else "gguf" if target_format == "GGUF" else None

            if sync_lmstudio_preset_metadata(
                preset,
                resolved_model_id=target_model_id,
                probed_quant=target_quant,
                raw_format=target_raw_format,
            ):
                logger.info(
                    "Run %s: reconciled LM Studio preset %s -> %s",
                    self.run_id,
                    preset_id,
                    target_model_id,
                )

            snapshot_model["model_id"] = target_model_id
            snapshot_model["quantization"] = target_quant
            snapshot_model["model_format"] = target_format
            snapshot_changed = True

            generations = self.db.query(Generation).filter(
                Generation.question_id.in_(question_ids),
                Generation.model_preset_id == preset_id,
            ).all()
            for gen in generations:
                if gen.status == TaskStatus.success and gen.model_version == target_model_id:
                    continue
                affected_question_ids.add(gen.question_id)
                self.db.delete(gen)

        if affected_question_ids:
            self.db.query(Judgment).filter(
                Judgment.question_id.in_(affected_question_ids)
            ).delete(synchronize_session=False)

        if snapshot_changed or affected_question_ids:
            self.benchmark_run.run_config_snapshot = copy.deepcopy(snapshot)
            flag_modified(self.benchmark_run, "run_config_snapshot")
            self.db.commit()
            self.db.expire_all()

    async def run(self):
        """Execute the complete benchmark run."""
        if not self.benchmark_run:
            return

        # Generate and store random seed for reproducibility
        if not self.benchmark_run.random_seed:
            self.benchmark_run.random_seed = random_module.randint(0, 2**31 - 1)
            self.db.commit()

        random_module.seed(self.benchmark_run.random_seed)

        self.benchmark_run.status = RunStatus.running
        self.db.commit()

        try:
            # Load presets
            model_presets = {
                p.id: p for p in
                self.db.query(ModelPreset).filter(ModelPreset.id.in_(self.benchmark_run.model_ids)).all()
            }
            judge_presets = {
                p.id: p for p in
                self.db.query(ModelPreset).filter(ModelPreset.id.in_(self.benchmark_run.judge_ids)).all()
            }

            questions = self.db.query(Question).filter(
                Question.benchmark_id == self.benchmark_run.id
            ).order_by(Question.order).all()

            await self._reconcile_lmstudio_snapshot_variants(questions, model_presets)

            total_tasks = len(questions)

            # Resolve display labels for WebSocket progress (disambiguates same-name models)
            all_presets = list(model_presets.values()) + list(judge_presets.values())
            self._resolved_labels = resolve_display_labels(all_presets)

            model_names = [self._label(p) for p in model_presets.values()]
            judge_names = [self._label(p) for p in judge_presets.values()]
            print(f"[Run {self.run_id}] Starting '{self.benchmark_run.name}'")
            print(f"[Run {self.run_id}] Models: {model_names}")
            print(f"[Run {self.run_id}] Judges: {judge_names}")
            print(f"[Run {self.run_id}] Questions: {len(questions)}")

            # Phase 1: Generation (model-first for LM Studio, parallel for cloud)
            print(f"[Run {self.run_id}] === GENERATION PHASE ===")
            await manager.send_status(self.run_id, "generating", 0)
            watchdog_task = asyncio.create_task(self._watchdog())
            try:
                await self._run_generation_phase(questions, model_presets)

                # Checkpoint: create any missing generations and retry failed/stuck ones
                # Expire stale identity map — generations were updated by separate sessions
                self.db.expire_all()
                await self._create_missing_generations(questions, model_presets)
                await self._retry_failed_generations(model_presets)
            finally:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

            # Phase 2: Judging — all tasks fire at once, semaphores throttle per-provider
            print(f"[Run {self.run_id}] === JUDGING PHASE ===")
            await manager.send_status(self.run_id, "judging", 50)
            judgment_watchdog_task = asyncio.create_task(self._judgment_watchdog())
            try:
                await self._judge_all_questions(questions, self.benchmark_run, judge_presets)

                if self.cancelled:
                    self.benchmark_run.status = RunStatus.cancelled
                    self.db.commit()
                    await manager.send_status(self.run_id, "cancelled", 0)
                    return

                # Checkpoint: retry failed judgments
                self.db.expire_all()
                await self._retry_failed_judgments(self.benchmark_run, judge_presets)
            finally:
                judgment_watchdog_task.cancel()
                try:
                    await judgment_watchdog_task
                except asyncio.CancelledError:
                    pass

            # Phase 3: Comment summarization (optional, non-blocking)
            print(f"[Run {self.run_id}] === SUMMARIZATION PHASE ===")
            self.benchmark_run.status = RunStatus.summarizing
            self.db.commit()
            try:
                await self._run_summarization_phase(questions, judge_presets, model_presets)
            except Exception as e:
                logger.warning(f"Comment summarization phase failed (non-fatal): {e}")

            # Calculate total context tokens from all questions
            self.db.expire_all()
            total_context_tokens = sum(q.context_tokens or 0 for q in questions)
            self.benchmark_run.total_context_tokens = total_context_tokens

            # Complete
            self.benchmark_run.status = RunStatus.completed
            self.benchmark_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            # Update ELO ratings after successful completion
            self._update_elo_on_completion()

            print(f"[Run {self.run_id}] === COMPLETE ===")
            await manager.send_status(self.run_id, "completed", 100)

        except Exception as e:
            self.benchmark_run.status = RunStatus.failed
            self.db.commit()
            await manager.send_status(self.run_id, "failed", 0)
            raise

    async def resume(self):
        """Resume a benchmark from where it left off, filling in missing generations and judgments."""
        if not self.benchmark_run:
            return

        self.benchmark_run.status = RunStatus.running
        self.db.commit()

        if self.benchmark_run.random_seed:
            random_module.seed(self.benchmark_run.random_seed)

        try:
            # Load presets
            model_presets = {
                p.id: p for p in
                self.db.query(ModelPreset).filter(ModelPreset.id.in_(self.benchmark_run.model_ids)).all()
            }
            judge_presets = {
                p.id: p for p in
                self.db.query(ModelPreset).filter(ModelPreset.id.in_(self.benchmark_run.judge_ids)).all()
            }

            questions = self.db.query(Question).filter(
                Question.benchmark_id == self.benchmark_run.id
            ).order_by(Question.order).all()

            await self._reconcile_lmstudio_snapshot_variants(questions, model_presets)

            total_tasks = len(questions)

            # Resolve display labels for WebSocket progress
            all_presets = list(model_presets.values()) + list(judge_presets.values())
            self._resolved_labels = resolve_display_labels(all_presets)

            model_names = [self._label(p) for p in model_presets.values()]
            judge_names = [self._label(p) for p in judge_presets.values()]
            print(f"[Run {self.run_id}] Resuming '{self.benchmark_run.name}'")
            print(f"[Run {self.run_id}] Models: {model_names}")
            print(f"[Run {self.run_id}] Judges: {judge_names}")
            print(f"[Run {self.run_id}] Questions: {len(questions)}")

            # Phase 1: Generate missing generations (model-first for LM Studio)
            print(f"[Run {self.run_id}] === GENERATION PHASE ===")
            await manager.send_status(self.run_id, "generating", 0)
            watchdog_task = asyncio.create_task(self._watchdog())
            try:
                await self._run_generation_phase(questions, model_presets, skip_existing=True)

                # Checkpoint: create any missing generations and retry failed/stuck ones
                self.db.expire_all()
                await self._create_missing_generations(questions, model_presets)
                await self._retry_failed_generations(model_presets)
            finally:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

            # Phase 2: Clear any remaining judgments and re-judge all questions
            # (resume endpoint already clears these, but this is defense-in-depth)
            for question in questions:
                self.db.query(Judgment).filter(
                    Judgment.question_id == question.id
                ).delete()
            self.db.commit()

            print(f"[Run {self.run_id}] === JUDGING PHASE ===")
            await manager.send_status(self.run_id, "judging", 50)
            judgment_watchdog_task = asyncio.create_task(self._judgment_watchdog())
            try:
                await self._judge_all_questions(questions, self.benchmark_run, judge_presets)

                if self.cancelled:
                    self.benchmark_run.status = RunStatus.cancelled
                    self.db.commit()
                    await manager.send_status(self.run_id, "cancelled", 0)
                    return

                # Checkpoint: retry failed judgments
                self.db.expire_all()
                await self._retry_failed_judgments(self.benchmark_run, judge_presets)
            finally:
                judgment_watchdog_task.cancel()
                try:
                    await judgment_watchdog_task
                except asyncio.CancelledError:
                    pass

            # Phase 3: Comment summarization (optional, non-blocking)
            print(f"[Run {self.run_id}] === SUMMARIZATION PHASE ===")
            self.benchmark_run.status = RunStatus.summarizing
            self.db.commit()
            try:
                await self._run_summarization_phase(questions, judge_presets, model_presets)
            except Exception as e:
                logger.warning(f"Comment summarization phase failed (non-fatal): {e}")

            # Calculate total context tokens from all questions
            self.db.expire_all()
            total_context_tokens = sum(q.context_tokens or 0 for q in questions)
            self.benchmark_run.total_context_tokens = total_context_tokens

            # Complete
            self.benchmark_run.status = RunStatus.completed
            self.benchmark_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            # Update ELO ratings after successful completion
            self._update_elo_on_completion()

            print(f"[Run {self.run_id}] === COMPLETE ===")
            await manager.send_status(self.run_id, "completed", 100)

        except Exception as e:
            self.benchmark_run.status = RunStatus.failed
            self.db.commit()
            await manager.send_status(self.run_id, "failed", 0)
            raise

    async def _run_generation_phase(self, questions: list, model_presets: Dict[int, ModelPreset],
                                     skip_existing: bool = False):
        """Run the generation phase with model-first ordering for LM Studio.

        LM Studio models on the same server use model-first ordering:
            Load Model1 → all questions → Load Model2 → all questions
        This minimizes expensive model swaps on local inference servers.

        Cloud APIs run in parallel per-model (each model processes questions sequentially).

        Args:
            skip_existing: If True (resume mode), skip (question, model) pairs that already have generations.
        """
        from app.db.models import ProviderType

        # When resuming, find successful generation pairs to skip
        existing_pairs = set()
        if skip_existing:
            for gen in self.db.query(Generation).join(Question).filter(
                Question.benchmark_id == self.run_id,
                Generation.status == TaskStatus.success
            ).all():
                existing_pairs.add((gen.question_id, gen.model_preset_id))
            # Delete stuck pending/failed generations so they get recreated fresh
            stuck = self.db.query(Generation).join(Question).filter(
                Question.benchmark_id == self.run_id,
                Generation.status.in_([TaskStatus.pending, TaskStatus.failed])
            ).all()
            for gen in stuck:
                self.db.delete(gen)
            if stuck:
                self.db.commit()
                logger.info(f"Cleaned up {len(stuck)} stuck/failed generations for resume")

        # Group models by execution strategy
        lmstudio_servers: Dict[str, Dict[int, ModelPreset]] = {}
        cloud_models: Dict[int, ModelPreset] = {}

        for model_id, preset in model_presets.items():
            if preset.provider == ProviderType.lmstudio:
                server_key = await _resolve_lmstudio_server_key(preset.base_url)
                if server_key not in lmstudio_servers:
                    lmstudio_servers[server_key] = {}
                lmstudio_servers[server_key][model_id] = preset
            else:
                cloud_models[model_id] = preset

        # Count total generation tasks for progress tracking
        total_gen_tasks = 0
        for question in questions:
            for model_id in model_presets:
                if (question.id, model_id) not in existing_pairs:
                    total_gen_tasks += 1

        if total_gen_tasks == 0:
            return

        completed = [0]

        async def update_progress():
            progress = int(completed[0] / total_gen_tasks * 50)
            await manager.send_status(self.run_id, "generating", progress)

        # --- LM Studio: model-first (load each model once, run ALL questions) ---
        async def run_lmstudio_server(server_key: str, server_models: Dict[int, ModelPreset]):
            import time as _time
            server_label = server_key.replace("lmstudio_", "")
            model_list = [self._label(p) for p in server_models.values()]
            print(f"[Run {self.run_id}] Server {server_label}: {len(server_models)} models queued: {model_list}")

            for model_idx, (model_id, preset) in enumerate(server_models.items(), 1):
                if self.cancelled:
                    return

                label = self._label(preset)
                q_count = sum(1 for q in questions if (q.id, model_id) not in existing_pairs)
                print(f"[Run {self.run_id}] Server {server_label}: [{model_idx}/{len(server_models)}] Loading {label}")

                # Load model once for all questions
                load_start = _time.time()
                await ensure_lmstudio_model(preset.base_url, preset.model_id)
                print(f"[Run {self.run_id}] Server {server_label}: {label} ready ({_time.time() - load_start:.1f}s), generating {q_count} questions")

                for question in questions:
                    if self.cancelled:
                        return
                    if (question.id, model_id) in existing_pairs:
                        continue

                    gen = Generation(
                        question_id=question.id,
                        model_preset_id=model_id,
                        status=TaskStatus.pending
                    )
                    self.db.add(gen)
                    self.db.commit()

                    gen_start = _time.time()
                    await self._generate_with_retry(
                        gen.id, preset, question.id,
                        question.system_prompt, question.user_prompt, self._label(preset)
                    )

                    completed[0] += 1
                    await update_progress()
                    print(f"[Run {self.run_id}] Server {server_label}: {label} Q{question.order + 1} done ({_time.time() - gen_start:.1f}s) [{completed[0]}/{total_gen_tasks}]")

                print(f"[Run {self.run_id}] Server {server_label}: {label} — all {q_count} questions complete")

        # --- Cloud/other: parallel per-model, sequential per-question ---
        async def run_cloud_model(model_id: int, preset: ModelPreset):
            import time as _time
            label = self._label(preset)
            q_count = sum(1 for q in questions if (q.id, model_id) not in existing_pairs)
            print(f"[Run {self.run_id}] Cloud: {label} — generating {q_count} questions")

            for question in questions:
                if self.cancelled:
                    return
                if (question.id, model_id) in existing_pairs:
                    continue

                gen = Generation(
                    question_id=question.id,
                    model_preset_id=model_id,
                    status=TaskStatus.pending
                )
                self.db.add(gen)
                self.db.commit()

                gen_start = _time.time()
                await self._generate_with_retry(
                    gen.id, preset, question.id,
                    question.system_prompt, question.user_prompt, self._label(preset)
                )

                completed[0] += 1
                await update_progress()
                print(f"[Run {self.run_id}] Cloud: {label} Q{question.order + 1} done ({_time.time() - gen_start:.1f}s) [{completed[0]}/{total_gen_tasks}]")

            print(f"[Run {self.run_id}] Cloud: {label} — all {q_count} questions complete")

        # Run all strategies in parallel
        tasks = []
        for server_key, server_models in lmstudio_servers.items():
            tasks.append(run_lmstudio_server(server_key, server_models))
        for model_id, preset in cloud_models.items():
            tasks.append(run_cloud_model(model_id, preset))

        print(f"[Run {self.run_id}] Generation: {len(lmstudio_servers)} server(s), {len(cloud_models)} cloud, {total_gen_tasks} total")
        import time as _time
        phase_start = _time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Generation task failed: {type(result).__name__}: {result}")
                print(f"[Run {self.run_id}] Generation FAILED: {type(result).__name__}: {result}")

        print(f"[Run {self.run_id}] Generation complete: {completed[0]}/{total_gen_tasks} in {_time.time() - phase_start:.1f}s")

    async def _generate_with_retry(self, gen_id: int, preset: ModelPreset, question_id: int,
                                   system_prompt: str, user_prompt: str, preset_name: str):
        """Generate with automatic retries using per-task session."""
        from app.db.database import SessionLocal

        thinking_only_retried = False

        for attempt in range(MAX_RETRIES):
            if self.cancelled:
                return

            db = SessionLocal()
            try:
                gen = db.query(Generation).filter(Generation.id == gen_id).first()
                if not gen:
                    return

                gen.status = TaskStatus.running
                gen.retries = attempt
                gen.started_at = datetime.now(timezone.utc)
                db.commit()

                if attempt > 0:
                    await manager.send_generation(
                        self.run_id, question_id, preset_name,
                        "retry", retry=attempt
                    )
                    await asyncio.sleep(RETRY_DELAYS[attempt - 1])
                else:
                    # Broadcast running status on first attempt
                    await manager.send_generation(
                        self.run_id, question_id, preset_name,
                        "running"
                    )

                # Load attachments for this question
                question_attachments = db.query(QuestionAttachment).filter(
                    QuestionAttachment.question_id == question_id
                ).options(joinedload(QuestionAttachment.attachment)).all()

                attachment_list = None
                if question_attachments:
                    attachment_list = []
                    for qa in question_attachments:
                        attachment_list.append({
                            "storage_path": qa.attachment.storage_path,
                            "mime_type": qa.attachment.mime_type,
                            "filename": qa.attachment.filename
                        })

                # Resolve temperature based on mode and preset
                temp_mode = self.benchmark_run.temperature_mode or TemperatureMode.normalized
                temperature = resolve_temperature(
                    preset, temp_mode, self.benchmark_run.temperature
                )

                try:
                    result = await asyncio.wait_for(
                        self._throttled_generate(
                            preset, system_prompt, user_prompt,
                            temperature=temperature,
                            attachments=attachment_list,
                        ),
                        timeout=PER_ATTEMPT_GEN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    # httpx's per-chunk read timeout does NOT catch slow-drip
                    # hangs (e.g. OpenRouter sending one keepalive byte every
                    # few minutes). This outer wall-clock cap is what actually
                    # breaks such hangs. Fall through to next retry iteration.
                    logger.warning(
                        "[Run %s] Gen: %s Q%s attempt %d/%d wall-clock timeout after %ds",
                        self.run_id, preset_name, question_id, attempt + 1,
                        MAX_RETRIES, PER_ATTEMPT_GEN_TIMEOUT,
                    )
                    gen.error = (
                        f"Attempt {attempt+1}/{MAX_RETRIES} wall-clock timeout "
                        f"after {PER_ATTEMPT_GEN_TIMEOUT}s"
                    )
                    gen.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    continue
                except asyncio.CancelledError:
                    gen.status = TaskStatus.failed
                    gen.error = "Cancelled"
                    gen.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    raise

                if result["success"]:
                    # Thinking-only: model spent all tokens reasoning, no answer text.
                    # Retry once — non-deterministic, may produce an answer on second try.
                    if result.get("thinking_only") and not thinking_only_retried:
                        thinking_only_retried = True
                        tokens = result.get("tokens", 0)
                        logger.warning(
                            "[Run %s] Gen: %s Q%s thinking-only (%d tokens, no answer) — retrying",
                            self.run_id, preset_name, question_id, tokens
                        )
                        gen.error = f"Thinking-only ({tokens} tokens, no answer) — retrying"
                        gen.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        await manager.send_generation(
                            self.run_id, question_id, preset_name,
                            "retry", retry=attempt + 1
                        )
                        db.close()
                        continue

                    gen.status = TaskStatus.success
                    gen.content = result["content"]
                    gen.tokens = result.get("tokens")
                    gen.input_tokens = result.get("input_tokens")
                    gen.output_tokens = result.get("output_tokens")
                    gen.cached_input_tokens = result.get("cached_input_tokens")
                    gen.reasoning_tokens = result.get("reasoning_tokens")
                    gen.raw_chars = result.get("raw_chars")
                    gen.answer_chars = result.get("answer_chars")
                    gen.latency_ms = result.get("latency_ms")
                    gen.model_version = result.get("model_version")
                    gen.error = None
                    gen.completed_at = datetime.now(timezone.utc)
                    db.commit()

                    # Update question context tokens if estimated
                    if result.get("estimated_tokens"):
                        question = db.query(Question).filter(Question.id == question_id).first()
                        if question:
                            question.context_tokens = result["estimated_tokens"]
                            db.commit()

                    print(f"[Run {self.run_id}] Gen: {preset_name} Q{question_id} OK — {gen.tokens or 0}tok, {gen.latency_ms or 0}ms")
                    await manager.send_generation(
                        self.run_id, question_id, preset_name,
                        "success", tokens=gen.tokens, preview=gen.content
                    )
                    return

                gen.error = result["error"]
                db.commit()
                print(f"[Run {self.run_id}] Gen: {preset_name} Q{question_id} attempt {attempt + 1} FAILED: {result['error'][:150]}")

            finally:
                db.close()

        # All retries failed
        db = SessionLocal()
        try:
            gen = db.query(Generation).filter(Generation.id == gen_id).first()
            if gen:
                gen.status = TaskStatus.failed
                gen.completed_at = datetime.now(timezone.utc)
                db.commit()

                print(f"[Run {self.run_id}] Gen: {preset_name} Q{question_id} ALL {MAX_RETRIES} RETRIES EXHAUSTED")
                await manager.send_generation(
                    self.run_id, question_id, preset_name,
                    "failed", error=gen.error
                )
        finally:
            db.close()

    async def _judge_question(self, question: Question, run: BenchmarkRun, judge_presets: Dict[int, ModelPreset]):
        """Judge a question with all judges.

        Groups judges by server and runs sequentially within each server
        to avoid model loading conflicts on LM Studio.
        """
        from app.db.models import ProviderType

        generations = self.db.query(Generation).filter(
            Generation.question_id == question.id,
            Generation.status == TaskStatus.success
        ).all()

        if not generations:
            return  # Nothing to judge

        # Extract question data before concurrent tasks
        question_id = question.id
        system_prompt = question.system_prompt
        user_prompt = question.user_prompt
        expected_answer = getattr(question, 'expected_answer', None)
        criteria = run.criteria

        # Helper to group tasks by server
        async def get_server_key(preset: ModelPreset) -> str:
            if preset.provider == ProviderType.lmstudio:
                return await _resolve_lmstudio_server_key(preset.base_url)
            return f"cloud_{preset.id}"

        if run.judge_mode == JudgeMode.comparison:
            # One judgment per judge comparing all models
            gen_dict = {g.model_preset_id: g.content for g in generations}

            # Group judges by server
            server_groups: Dict[str, List[tuple]] = {}
            for judge_id, preset in judge_presets.items():
                judgment = Judgment(
                    question_id=question_id,
                    judge_preset_id=judge_id,
                    status=TaskStatus.pending
                )
                self.db.add(judgment)
                self.db.commit()
                judgment_id = judgment.id

                server_key = await get_server_key(preset)
                if server_key not in server_groups:
                    server_groups[server_key] = []
                server_groups[server_key].append((judgment_id, preset, self._label(preset)))

            async def run_comparison_group(server_key: str, items: List[tuple]):
                for judgment_id, preset, preset_name in items:
                    try:
                        if server_key.startswith("lmstudio_"):
                            print(f"[Run {self.run_id}] Judge {preset_name}: loading on {server_key.replace('lmstudio_', '')}")
                            await ensure_lmstudio_model(preset.base_url, preset.model_id)
                        # No outer wait_for: per-attempt timeouts inside
                        # _judge_comparison_with_retry bound the actual API
                        # call time. Queue wait is unbounded by design so the
                        # retry loop gets its full 3-attempt budget even if the
                        # provider semaphore is saturated.
                        await self._judge_comparison_with_retry(
                            judgment_id, preset, question_id, system_prompt, user_prompt,
                            gen_dict, criteria, preset_name, expected_answer=expected_answer
                        )
                        print(f"[Run {self.run_id}] Judge {preset_name}: Q{question.order + 1} done")
                    except Exception as e:
                        logger.error(f"Judgment {judgment_id} crashed: {e}")
                        self._mark_judgment_failed(judgment_id, f"Unexpected error: {e}")
                        await manager.send_judgment(
                            self.run_id, question_id, preset_name,
                            "failed", error=str(e)
                        )

            await asyncio.gather(*[run_comparison_group(key, items) for key, items in server_groups.items()])
        else:
            # Separate mode: one judgment per (judge, generation) pair
            server_groups: Dict[str, List[tuple]] = {}
            for gen in generations:
                gen_content = gen.content
                gen_model_id = gen.model_preset_id
                gen_id = gen.id

                for judge_id, preset in judge_presets.items():
                    judgment = Judgment(
                        question_id=question_id,
                        judge_preset_id=judge_id,
                        generation_id=gen_id,
                        status=TaskStatus.pending
                    )
                    self.db.add(judgment)
                    self.db.commit()
                    judgment_id = judgment.id

                    server_key = await get_server_key(preset)
                    if server_key not in server_groups:
                        server_groups[server_key] = []
                    server_groups[server_key].append((judgment_id, preset, gen_content, gen_model_id, self._label(preset)))

            async def run_separate_group(server_key: str, items: List[tuple]):
                for judgment_id, preset, gen_content, gen_model_id, preset_name in items:
                    try:
                        if server_key.startswith("lmstudio_"):
                            print(f"[Run {self.run_id}] Judge {preset_name}: loading on {server_key.replace('lmstudio_', '')}")
                            await ensure_lmstudio_model(preset.base_url, preset.model_id)
                        # No outer wait_for — see run_comparison_group note.
                        await self._judge_separate_with_retry(
                            judgment_id, preset, question_id, system_prompt, user_prompt,
                            gen_content, gen_model_id, criteria, preset_name,
                            expected_answer=expected_answer
                        )
                        print(f"[Run {self.run_id}] Judge {preset_name}: Q{question.order + 1} done")
                    except Exception as e:
                        logger.error(f"Judgment {judgment_id} crashed: {e}")
                        self._mark_judgment_failed(judgment_id, f"Unexpected error: {e}")
                        await manager.send_judgment(
                            self.run_id, question_id, preset_name,
                            "failed", error=str(e)
                        )

            await asyncio.gather(*[run_separate_group(key, items) for key, items in server_groups.items()])

    async def _judge_all_questions(self, questions: list, run: BenchmarkRun,
                                    judge_presets: Dict[int, ModelPreset]):
        """Judge all questions concurrently — semaphores throttle per provider.

        Instead of awaiting all judges per question before moving to the next,
        this fires judgment tasks for ALL questions at once. Fast providers
        (Anthropic, OpenAI) race ahead while slow ones (Kimi) process at their
        own pace, with zero idle time for anyone.

        Per-server grouping inside _judge_question still prevents parallel
        model loads on the same LM Studio server.
        """
        total_judgments = len(questions)
        if total_judgments == 0:
            return

        completed = [0]

        async def judge_one_question(question: Question):
            if self.cancelled:
                return
            await self._judge_question(question, run, judge_presets)
            completed[0] += 1
            progress = 50 + int(completed[0] / total_judgments * 45)
            await manager.send_status(self.run_id, "judging", progress)

        # Fire ALL question judgment tasks at once — per-server grouping inside
        # _judge_question still prevents parallel LM Studio model loads
        await asyncio.gather(*[
            judge_one_question(question)
            for question in questions
        ], return_exceptions=True)

    async def _judge_comparison_with_retry(self, judgment_id: int, preset: ModelPreset,
                                           question_id: int, system_prompt: str, user_prompt: str,
                                           generations: Dict[int, str], criteria: list, preset_name: str,
                                           expected_answer: Optional[str] = None):
        """Judge in comparison mode with retries using per-task session.

        The semaphore is acquired BEFORE the judgment is marked `running` so the
        UI/watchdog only see tasks that are actually executing — not ones queued
        behind the per-provider concurrency limit. Retry backoff sleeps happen
        OUTSIDE the semaphore so a sleeping retry never wastes a slot.
        """
        from app.db.database import SessionLocal

        sem = await self._get_semaphore(preset)

        for attempt in range(MAX_RETRIES):
            if self.cancelled:
                return

            # Backoff sleep happens BEFORE semaphore acquisition so we don't
            # block other tasks while waiting to retry.
            if attempt > 0:
                await asyncio.sleep(RETRY_DELAYS[attempt - 1])

            async with sem:
                if self.cancelled:
                    return

                db = SessionLocal()
                try:
                    judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
                    if not judgment:
                        return

                    judgment.status = TaskStatus.running
                    judgment.retries = attempt
                    db.commit()

                    await manager.send_judgment(
                        self.run_id, question_id, preset_name,
                        "retry" if attempt > 0 else "running",
                        retry=attempt if attempt > 0 else None,
                    )

                    # Resolve judge temperature
                    temp_mode = self.benchmark_run.temperature_mode or TemperatureMode.normalized
                    judge_temp = resolve_temperature(
                        preset, temp_mode, self.benchmark_run.temperature
                    )

                    try:
                        result = await asyncio.wait_for(
                            judge_comparison(
                                preset, system_prompt, user_prompt,
                                generations, criteria, judge_temp,
                                expected_answer=expected_answer
                            ),
                            timeout=PER_ATTEMPT_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        # This attempt's API call exceeded PER_ATTEMPT_TIMEOUT.
                        # Record and fall through to the next retry iteration.
                        logger.warning(
                            f"Judgment {judgment_id} attempt {attempt+1}/{MAX_RETRIES} "
                            f"timed out after {PER_ATTEMPT_TIMEOUT}s"
                        )
                        judgment.error = (
                            f"Attempt {attempt+1}/{MAX_RETRIES} timed out after "
                            f"{PER_ATTEMPT_TIMEOUT}s"
                        )
                        db.commit()
                        continue
                    except asyncio.CancelledError:
                        judgment.status = TaskStatus.failed
                        judgment.error = "Cancelled"
                        judgment.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        raise

                    if result["success"]:
                        judgment.status = TaskStatus.success
                        judgment.blind_mapping = result["blind_mapping"]
                        judgment.presentation_mapping = result.get("presentation_mapping")
                        judgment.rankings = result["rankings"]
                        judgment.scores = result["scores"]
                        judgment.comments = result.get("comments")
                        judgment.score_rationales = result.get("score_rationales")
                        judgment.reasoning = result["reasoning"]
                        judgment.latency_ms = result.get("latency_ms")
                        judgment.tokens = result.get("tokens")
                        judgment.input_tokens = result.get("input_tokens")
                        judgment.output_tokens = result.get("output_tokens")
                        judgment.cached_input_tokens = result.get("cached_input_tokens")
                        judgment.reasoning_tokens = result.get("reasoning_tokens")
                        judgment.judge_temperature = result.get("temperature")
                        judgment.error = None
                        judgment.completed_at = datetime.now(timezone.utc)
                        db.commit()

                        # Determine winner name
                        winner_label = result["rankings"][0]
                        winner_id = result["blind_mapping"][winner_label]
                        winner_preset = db.query(ModelPreset).filter(ModelPreset.id == winner_id).first()

                        await manager.send_judgment(
                            self.run_id, question_id, preset_name,
                            "success", winner=self._label(winner_preset) if winner_preset else "Unknown"
                        )
                        return

                    judgment.error = result["error"]
                    db.commit()

                finally:
                    db.close()

        # All retries failed
        db = SessionLocal()
        try:
            judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
            if judgment:
                judgment.status = TaskStatus.failed
                judgment.completed_at = datetime.now(timezone.utc)
                db.commit()

                await manager.send_judgment(
                    self.run_id, question_id, preset_name,
                    "failed", error=judgment.error
                )
        finally:
            db.close()

    async def _judge_separate_with_retry(self, judgment_id: int, preset: ModelPreset,
                                         question_id: int, system_prompt: str, user_prompt: str,
                                         generation_content: str, generation_model_id: int,
                                         criteria: list, preset_name: str,
                                         expected_answer: Optional[str] = None):
        """Judge in separate mode with retries using per-task session.

        Same semaphore-before-status-flip shape as _judge_comparison_with_retry.
        """
        from app.db.database import SessionLocal

        sem = await self._get_semaphore(preset)

        for attempt in range(MAX_RETRIES):
            if self.cancelled:
                return

            if attempt > 0:
                await asyncio.sleep(RETRY_DELAYS[attempt - 1])

            async with sem:
                if self.cancelled:
                    return

                db = SessionLocal()
                try:
                    judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
                    if not judgment:
                        return

                    judgment.status = TaskStatus.running
                    judgment.retries = attempt
                    db.commit()

                    await manager.send_judgment(
                        self.run_id, question_id, preset_name,
                        "retry" if attempt > 0 else "running",
                        retry=attempt if attempt > 0 else None,
                    )

                    # Resolve judge temperature
                    temp_mode = self.benchmark_run.temperature_mode or TemperatureMode.normalized
                    judge_temp = resolve_temperature(
                        preset, temp_mode, self.benchmark_run.temperature
                    )

                    try:
                        result = await asyncio.wait_for(
                            judge_separate(
                                preset, system_prompt, user_prompt,
                                generation_content, criteria, judge_temp,
                                expected_answer=expected_answer
                            ),
                            timeout=PER_ATTEMPT_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Judgment {judgment_id} attempt {attempt+1}/{MAX_RETRIES} "
                            f"timed out after {PER_ATTEMPT_TIMEOUT}s"
                        )
                        judgment.error = (
                            f"Attempt {attempt+1}/{MAX_RETRIES} timed out after "
                            f"{PER_ATTEMPT_TIMEOUT}s"
                        )
                        db.commit()
                        continue
                    except asyncio.CancelledError:
                        judgment.status = TaskStatus.failed
                        judgment.error = "Cancelled"
                        judgment.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        raise

                    if result["success"]:
                        judgment.status = TaskStatus.success
                        judgment.scores = {generation_model_id: result["scores"]}
                        judgment.comments = {generation_model_id: result.get("comments", [])}
                        judgment.score_rationales = {
                            generation_model_id: result["score_rationale"]
                        }
                        judgment.reasoning = result["reasoning"]
                        judgment.latency_ms = result.get("latency_ms")
                        judgment.tokens = result.get("tokens")
                        judgment.input_tokens = result.get("input_tokens")
                        judgment.output_tokens = result.get("output_tokens")
                        judgment.cached_input_tokens = result.get("cached_input_tokens")
                        judgment.reasoning_tokens = result.get("reasoning_tokens")
                        judgment.judge_temperature = result.get("temperature")
                        judgment.error = None
                        judgment.completed_at = datetime.now(timezone.utc)
                        db.commit()

                        await manager.send_judgment(
                            self.run_id, question_id, preset_name,
                            "success", scores=result["scores"]
                        )
                        return

                    judgment.error = result["error"]
                    db.commit()

                finally:
                    db.close()

        # All retries failed
        db = SessionLocal()
        try:
            judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
            if judgment:
                judgment.status = TaskStatus.failed
                judgment.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    async def _create_missing_generations(self, questions: list, model_presets: Dict[int, ModelPreset]):
        """Create Generation rows for any (question, model) pairs that are missing.

        If a model coroutine crashes mid-flight (e.g. on question 2 of 10), questions 3-10
        never get Generation rows created. This sweep fills in those gaps so the retry
        checkpoint can pick them up.
        """
        existing = set()
        for gen in self.db.query(Generation).join(Question).filter(
            Question.benchmark_id == self.run_id
        ).all():
            existing.add((gen.question_id, gen.model_preset_id))

        created = 0
        for question in questions:
            for model_id in model_presets:
                if (question.id, model_id) not in existing:
                    gen = Generation(
                        question_id=question.id,
                        model_preset_id=model_id,
                        status=TaskStatus.pending
                    )
                    self.db.add(gen)
                    created += 1

        if created:
            self.db.commit()
            logger.info(f"Created {created} missing generation(s) for retry")

    async def _retry_failed_generations(self, model_presets: Dict[int, ModelPreset]):
        """Retry any failed or stuck generations one more time."""
        if self.cancelled:
            return

        # Catch failed AND stuck (running/pending) generations — a model coroutine may
        # have crashed mid-flight leaving rows in non-terminal state.
        stuck = self.db.query(Generation).join(Question).filter(
            Question.benchmark_id == self.run_id,
            Generation.status.in_([TaskStatus.failed, TaskStatus.running, TaskStatus.pending])
        ).all()

        if stuck:
            logger.info(f"Retrying {len(stuck)} failed/stuck generation(s) before judging")

        for gen in stuck:
            if self.cancelled:
                return
            question = gen.question
            preset = model_presets.get(gen.model_preset_id)
            if preset:
                logger.info(f"Retry checkpoint: {self._label(preset)} for Q{question.order + 1}")
                await self._generate_with_retry(
                    gen.id, preset, question.id, question.system_prompt,
                    question.user_prompt, self._label(preset)
                )

    async def _retry_failed_judgments(self, run: BenchmarkRun, judge_presets: Dict[int, ModelPreset]):
        """Retry failed/stuck judgments in multiple sweeps with increasing delays.

        Sweep 0 runs immediately. Subsequent sweeps wait SWEEP_DELAYS[i] seconds
        before retrying, giving rate limits and transient errors time to clear.
        Stops early if all judgments succeed or the run is cancelled.
        """
        for sweep_idx in range(len(SWEEP_DELAYS) + 1):
            if self.cancelled:
                return

            self.db.expire_all()
            failed = self.db.query(Judgment).join(Question).filter(
                Question.benchmark_id == self.run_id,
                Judgment.status.in_([TaskStatus.failed, TaskStatus.running, TaskStatus.pending])
            ).all()

            if not failed:
                return

            if sweep_idx > 0:
                delay = SWEEP_DELAYS[sweep_idx - 1]
                logger.info(
                    f"Retry sweep {sweep_idx}/{len(SWEEP_DELAYS)}: "
                    f"{len(failed)} failed judgment(s), waiting {delay}s before retrying"
                )
                await manager.send_status(self.run_id, "judging", 95)
                await asyncio.sleep(delay)
            else:
                logger.info(f"Retrying {len(failed)} failed/stuck judgment(s) (immediate sweep)")

            async def retry_one(judgment: Judgment):
                if self.cancelled:
                    return
                question = judgment.question
                preset = judge_presets.get(judgment.judge_preset_id)
                if not preset:
                    return

                expected_answer = getattr(question, 'expected_answer', None)

                try:
                    if run.judge_mode == JudgeMode.comparison:
                        generations = self.db.query(Generation).filter(
                            Generation.question_id == question.id,
                            Generation.status == TaskStatus.success
                        ).all()
                        gen_dict = {g.model_preset_id: g.content for g in generations}
                        await self._judge_comparison_with_retry(
                            judgment.id, preset, question.id, question.system_prompt,
                            question.user_prompt, gen_dict, run.criteria, self._label(preset),
                            expected_answer=expected_answer
                        )
                    else:
                        gen = judgment.generation
                        if gen:
                            await self._judge_separate_with_retry(
                                judgment.id, preset, question.id, question.system_prompt,
                                question.user_prompt, gen.content, gen.model_preset_id,
                                run.criteria, self._label(preset), expected_answer=expected_answer
                            )
                except Exception as e:
                    logger.error(f"Retry sweep {sweep_idx} judgment {judgment.id} crashed: {e}")
                    self._mark_judgment_failed(judgment.id, f"Retry sweep {sweep_idx} error: {e}")

            await asyncio.gather(
                *[retry_one(judgment) for judgment in failed],
                return_exceptions=True,
            )

    async def _run_summarization_phase(self, questions: list,
                                        judge_presets: Dict[int, ModelPreset],
                                        model_presets: Dict[int, ModelPreset]):
        """Summarize judge comments per model using each judge model.

        Collects all comments from each judge about each model across all questions,
        then asks the judge to synthesize them into a concise summary.

        Graceful: if summarization fails for any judge, we skip it and continue.
        """
        await manager.send_status(self.run_id, "summarizing", 96)

        all_preset_list = list(model_presets.values()) + list(judge_presets.values())
        resolved = resolve_display_labels(all_preset_list)

        # Collect comments: {judge_id: {model_name: [comments]}}
        judge_model_comments: Dict[int, Dict[str, list]] = {}

        for question in questions:
            judgments = self.db.query(Judgment).filter(
                Judgment.question_id == question.id,
                Judgment.status == TaskStatus.success
            ).all()

            for judgment in judgments:
                if not judgment.comments:
                    continue

                judge_id = judgment.judge_preset_id
                if judge_id not in judge_model_comments:
                    judge_model_comments[judge_id] = {}

                for model_id_str, comments in judgment.comments.items():
                    model_id = int(model_id_str) if isinstance(model_id_str, str) else model_id_str
                    model_name = resolved.get(model_id, model_presets[model_id].name) if model_id in model_presets else f"Model {model_id}"

                    if model_name not in judge_model_comments[judge_id]:
                        judge_model_comments[judge_id][model_name] = []
                    judge_model_comments[judge_id][model_name].extend(comments)

        if not judge_model_comments:
            return

        # Call each judge to summarize its comments (parallel across judges)
        comment_summaries = {}  # {judge_name: {model_name: "summary"}}

        async def summarize_for_judge(judge_id: int, model_comments: Dict[str, list]):
            preset = judge_presets.get(judge_id)
            if not preset:
                return
            judge_label = resolved.get(preset.id, preset.name)
            try:
                result = await summarize_judge_comments(preset, model_comments)
                if result["success"]:
                    comment_summaries[judge_label] = result["summaries"]
                else:
                    logger.warning(f"Comment summarization failed for judge {judge_label}: {result.get('error')}")
            except Exception as e:
                logger.warning(f"Comment summarization error for judge {judge_label}: {e}")

        await asyncio.gather(*[
            summarize_for_judge(judge_id, model_comments)
            for judge_id, model_comments in judge_model_comments.items()
        ], return_exceptions=True)

        self.benchmark_run.comment_summaries = comment_summaries if comment_summaries else None
        self.db.commit()


# Store active runners for cancellation
active_runners: Dict[int, BenchmarkRunner] = {}
