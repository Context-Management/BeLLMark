"""Seed default benchmark suites into the database."""
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal
from app.db.models import PromptSuite, PromptSuiteItem


SUITES_DIR = Path(__file__).parent.parent / "data" / "suites"


def seed_default_suites():
    """Seed all built-in benchmark suites. Idempotent — skips suites that already exist by name."""
    db = SessionLocal()
    try:
        suite_files = sorted(SUITES_DIR.glob("*.json"))
        if not suite_files:
            print("[SEED] No suite files found, skipping")
            return

        for suite_file in suite_files:
            data = json.loads(suite_file.read_text())

            # Skip if this specific suite already exists by name
            existing = db.query(PromptSuite).filter(
                PromptSuite.name == data["name"]
            ).first()
            if existing:
                continue

            suite = PromptSuite(
                name=data["name"],
                description=data.get("description", ""),
                default_criteria=data.get("default_criteria"),
            )
            db.add(suite)
            db.flush()

            for i, q in enumerate(data["questions"]):
                item = PromptSuiteItem(
                    suite_id=suite.id,
                    order=i + 1,
                    system_prompt=q.get("system_prompt", ""),
                    user_prompt=q["user_prompt"],
                    expected_answer=q.get("expected_answer", ""),
                )
                db.add(item)

            db.commit()
            print(f"[SEED] Loaded suite: {data['name']} ({len(data['questions'])} questions)")

    except Exception as e:
        print(f"[SEED] Error seeding suites: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_default_suites()
