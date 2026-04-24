from pydantic import BaseModel


class ConcurrencySettingResponse(BaseModel):
    provider: str
    server_key: str | None
    max_concurrency: int
    is_override: bool  # true if from DB, false if provider default


class ConcurrencySettingsListResponse(BaseModel):
    settings: list[ConcurrencySettingResponse]


class ConcurrencySettingUpdate(BaseModel):
    provider: str
    base_url: str | None = None
    max_concurrency: int | None  # null = reset to default
