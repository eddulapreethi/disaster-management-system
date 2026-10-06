from pydantic import BaseModel, ConfigDict, Field


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    resource_type: str = Field(min_length=1, max_length=60)
    quantity: int = Field(ge=0)
    unit: str = Field(default="units", min_length=1, max_length=30)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


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