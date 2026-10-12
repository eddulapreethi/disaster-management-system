from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.utc_timestamps import utc_isoformat


class AlertCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    severity: str = Field(pattern="^(low|moderate|high|critical)$")
    disaster_type: str = Field(min_length=1, max_length=40)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    severity: str
    disaster_type: str
    latitude: float | None
    longitude: float | None
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""