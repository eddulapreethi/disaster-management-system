import os
import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, assistant, auth, gis, hydrology, predictions, readiness, recommendations, resources, satellite, simulations, users, weather
from app.database.database import create_tables
from app.services.hydrology_service import run_hydrology_collector
from app.services.weather_service import run_weather_collector

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    collector_tasks = [
        asyncio.create_task(run_weather_collector(), name="open-meteo-minute-collector"),
        asyncio.create_task(run_hydrology_collector(), name="nwdp-hydrology-collector"),
    ]
    try:
        yield
    finally:
        for task in collector_tasks:
            task.cancel()
        await asyncio.gather(*collector_tasks, return_exceptions=True)


app = FastAPI(
    title="DisasterGuard AI API",
    description="Disaster risk, alert, simulation, GIS, and resource API.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(simulations.router, prefix="/api")
app.include_router(resources.router, prefix="/api")
app.include_router(gis.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(satellite.router, prefix="/api")
app.include_router(hydrology.router, prefix="/api")
app.include_router(readiness.router, prefix="/api")


@app.get("/")
def health_check():
    return {"status": "ok", "service": "DisasterGuard AI API"}


@app.get("/health")
def health_status():
    return health_check()