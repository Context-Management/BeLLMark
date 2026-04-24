# Database Migrations

## Manual Migration: Add raw_chars/answer_chars columns (2026-02)

If you have an existing `bellmark.db` from before this update, run:

```sql
ALTER TABLE generations ADD COLUMN raw_chars INTEGER;
ALTER TABLE generations ADD COLUMN answer_chars INTEGER;
```

Or simply delete `bellmark.db` to let SQLAlchemy recreate it.

## Manual Migration: Add price_input/price_output columns (2026-02)

For existing databases with model presets:

```sql
ALTER TABLE model_presets ADD COLUMN price_input REAL;
ALTER TABLE model_presets ADD COLUMN price_output REAL;
```

These columns are nullable. When null, the system uses default pricing
from `backend/app/core/pricing.py` based on provider and model_id.

## Manual Migration: Add reasoning fields (2026-02)

For existing databases with model presets:

```sql
ALTER TABLE model_presets ADD COLUMN is_reasoning INTEGER DEFAULT 0;
ALTER TABLE model_presets ADD COLUMN reasoning_level TEXT;
```

These columns add support for reasoning models (like OpenAI o1, o3):
- `is_reasoning`: 0 for standard models, 1 for reasoning-enabled models
- `reasoning_level`: One of: 'none', 'low', 'medium', 'high', 'xhigh' (nullable)

## Current Status

These manual migrations are superseded by Alembic, which now runs automatically on startup. See `backend/alembic/versions/` for the active migration chain. No manual SQL is needed for new installations.
