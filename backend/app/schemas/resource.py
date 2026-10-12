from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    resource_type: str = Field(min_length=1, max_length=60)
    quantity: int = Field(ge=0)
    unit: str = Field(default="units", min_length=1, max_length=30)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("name", "resource_type", "unit")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name, resource type, and unit cannot be blank.")
        return normalized


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    resource_type: str | None = Field(default=None, min_length=1, max_length=60)
    quantity: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("name", "resource_type", "unit")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name, resource type, and unit cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def require_changes(self) -> "ResourceUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one resource field must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Resource fields cannot be set to null.")
        return self


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    resource_type: str
    quantity: int
    unit: str
    latitude: float
    longitude: float
    status: str


class AllocationRequest(BaseModel):
    resource_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class ResourceDemand(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    resource_type: str = Field(min_length=1, max_length=60)
    quantity: int = Field(gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    priority_score: float = Field(default=0, ge=0, le=100)


class ResourcePlanRequest(BaseModel):
    demands: list[ResourceDemand] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_unique_demand_ids(self) -> "ResourcePlanRequest":
        identifiers = [demand.id for demand in self.demands]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Demand IDs must be unique within a resource plan.")
        return self