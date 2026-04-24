from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ConcurrencySetting
from app.schemas.concurrency import (
    ConcurrencySettingResponse,
    ConcurrencySettingsListResponse,
    ConcurrencySettingUpdate,
)
from app.core.concurrency import (
    PROVIDER_DEFAULTS,
    LOCAL_PROVIDERS,
    resolve_concurrency_key_sync,
)

router = APIRouter(prefix="/api/concurrency-settings", tags=["concurrency"])


@router.get("/", response_model=ConcurrencySettingsListResponse)
async def get_concurrency_settings(db: Session = Depends(get_db)):
    overrides = {(r.provider, r.server_key): r.max_concurrency
                 for r in db.query(ConcurrencySetting).all()}

    settings = []
    for provider, default in PROVIDER_DEFAULTS.items():
        key = (provider, None)
        settings.append(ConcurrencySettingResponse(
            provider=provider,
            server_key=None,
            max_concurrency=overrides.get(key, default),
            is_override=key in overrides,
        ))

    # Include any local-server overrides not covered by defaults
    for (prov, skey), val in overrides.items():
        if skey is not None:
            settings.append(ConcurrencySettingResponse(
                provider=prov, server_key=skey,
                max_concurrency=val, is_override=True,
            ))

    return ConcurrencySettingsListResponse(settings=settings)


@router.patch("/")
async def update_concurrency_setting(
    update: ConcurrencySettingUpdate,
    db: Session = Depends(get_db),
):
    if update.provider not in PROVIDER_DEFAULTS:
        raise HTTPException(400, f"Unknown provider: {update.provider}")

    provider, server_key = resolve_concurrency_key_sync(update.provider, update.base_url)

    existing = db.query(ConcurrencySetting).filter(
        ConcurrencySetting.provider == provider,
        ConcurrencySetting.server_key == server_key,
    ).first()

    if update.max_concurrency is None:
        # Reset to default
        if existing:
            db.delete(existing)
            db.commit()
        return {"status": "reset", "effective": PROVIDER_DEFAULTS[provider]}

    if update.max_concurrency < 1:
        raise HTTPException(400, "max_concurrency must be >= 1")

    if existing:
        existing.max_concurrency = update.max_concurrency
    else:
        db.add(ConcurrencySetting(
            provider=provider, server_key=server_key,
            max_concurrency=update.max_concurrency,
        ))
    db.commit()
    return {"status": "updated", "effective": update.max_concurrency}
