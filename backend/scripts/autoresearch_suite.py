"""CLI entrypoint for the overnight suite autoresearch workflow."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

from app.core.autoresearch import SuiteAutoresearchConfig, SuiteAutoresearchService
from app.db.database import SessionLocal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the BeLLMark overnight suite autoresearch loop.")
    parser.add_argument("--suite-id", type=int, default=None, help="Suite ID to refine. Defaults to the most-used completed suite.")
    parser.add_argument("--max-iterations", type=int, default=12, help="Maximum overnight refinement iterations.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Artifact directory. Defaults to results/autoresearch/<timestamp>.")
    parser.add_argument("--subject-model-ids", required=True, help="Comma-separated subject preset IDs (from your model_presets table).")
    parser.add_argument("--judge-model-ids", required=True, help="Comma-separated judge preset IDs.")
    parser.add_argument("--editor-model-id", type=int, required=True, help="Preset ID used to propose candidate rewrites.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call models; write baseline/result artifacts only.")
    return parser


def _parse_id_list(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


async def main_async(args: argparse.Namespace) -> int:
    output_dir = args.output_dir or Path("results") / "autoresearch" / datetime.now().strftime("%Y%m%d-%H%M%S")
    config = SuiteAutoresearchConfig(
        suite_id=args.suite_id,
        subject_model_ids=_parse_id_list(args.subject_model_ids),
        judge_model_ids=_parse_id_list(args.judge_model_ids),
        editor_model_id=args.editor_model_id,
        max_iterations=args.max_iterations,
        output_dir=output_dir,
        dry_run=args.dry_run,
    )

    db = SessionLocal()
    try:
        service = SuiteAutoresearchService(session=db, config=config)
        result = await service.run()
    finally:
        db.close()

    print(f"Suite ID: {result.suite_id}")
    print(f"Iterations completed: {result.iterations_completed}")
    print(f"Artifacts: {result.artifact_root}")
    print(f"Final suite: {result.final_suite_path}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
