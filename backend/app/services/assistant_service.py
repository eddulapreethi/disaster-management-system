from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.hydrological_observation import HydrologicalObservation
from app.models.prediction import Prediction
from app.models.resource import Resource
from app.models.simulation import Simulation
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.services.assistant_provider import (
    AssistantProviderError,
    AssistantProviderNotConfigured,
    get_assistant_provider,
)
from app.services.data_readiness_service import get_data_readiness, get_hydrology_status

ASSISTANT_DISCLAIMER = (
    "DisasterGuard is a decision-support tool, not an emergency authority. "
    "For urgent situations, follow official local emergency services."
)
logger = logging.getLogger(__name__)
PROJECT_DOCUMENTS = (
    ("backend/README.md", "Backend documentation"),
    ("frontend/README.md", "Frontend documentation"),
    ("ml/README.md", "Machine-learning documentation"),
    ("gis/README.md", "GIS documentation"),
    ("alerts/README.md", "Alert documentation"),
    ("resource-optimization/README.md", "Resource-planning documentation"),
)
PROJECT_DOCUMENT_STOP_WORDS = {
    "about", "does", "doesnt", "from", "have", "into", "that", "their", "there",
    "these", "this", "those", "what", "when", "where", "which", "with", "would",
    "currently", "disasterguard", "project", "application", "system",
}
PROJECT_GENERIC_QUERY_TERMS = {
    "app", "base", "based", "capability", "current", "feature", "implement",
    "model", "prediction", "project", "support", "system",
}

FRANCE_SOURCES = [
    {"title": "French flood risk governance (French government / flood risk management)", "url": "https://www.vigicrues.gouv.fr/"},
    {"title": "EU flood risk management overview", "url": "https://environment.ec.europa.eu/topics/water/floods_en"},
    {"title": "France flood risk policy and mapping guidance", "url": "https://www.preventiondesrisques.fr/"},
]

INDIA_SOURCES = [
    {"title": "India disaster management framework", "url": "https://ndma.gov.in/"},
    {"title": "CWC hydrological and flood forecasting resources", "url": "https://cwc.gov.in/"},
    {"title": "IMD weather and cyclone warnings", "url": "https://mausam.imd.gov.in/"},
]

VENICE_SOURCES = [
    {"title": "MOSE — Venice lagoon flood protection system", "url": "https://www.mosevenezia.eu/?lang=en"},
]

HEAT_DOME_SOURCES = [
    {
        "title": "Western North American extreme heat virtually impossible without human-caused climate change",
        "url": "https://www.worldweatherattribution.org/western-north-american-extreme-heat-virtually-impossible-without-human-caused-climate-change/",
    },
    {"title": "EPA: Heat islands", "url": "https://www.epa.gov/heatislands/what-are-heat-islands"},
]

HIGH_TIDE_FLOODING_SOURCES = [
    {
        "title": "NOAA: High tide flooding",
        "url": "https://oceanservice.noaa.gov/facts/high-tide-flooding.html",
    },
    {
        "title": "USGS: Karst aquifers",
        "url": "https://www.usgs.gov/centers/water-mission-area/science/karst-aquifers",
    },
]

CYCLONE_ROTATION_SOURCES = [
    {
        "title": "NOAA Ocean Service: The Coriolis effect",
        "url": "https://oceanservice.noaa.gov/education/tutorial_currents/04currents1.html",
    },
]

STORM_SURGE_SOURCES = [
    {
        "title": "National Hurricane Center: Storm surge overview",
        "url": "https://www.nhc.noaa.gov/surge/",
    },
]

FLOOD_SAFETY_SOURCES = [
    {"title": "National Disaster Response Force (NDRF)", "url": "https://www.ndrf.gov.in/"},
    {"title": "National Disaster Management Authority (NDMA)", "url": "https://ndma.gov.in/"},
]

GENERAL_ANSWERS = (
    (("what is a flood", "define a flood", "define flood", "meaning of a flood"), "A flood is an overflow of water onto land that is usually dry. It can result from intense or prolonged rainfall, river overflow, storm surge, rapid snow or ice melt, or drainage failure."),
    (("what is a cyclone", "what is a hurricane", "what is a typhoon", "define a tropical cyclone"), "A tropical cyclone is an organized rotating storm that forms over warm ocean water. It can bring damaging winds, heavy rain, coastal surge, and flooding. Regional names differ; use official local forecasts for current warnings."),
    (("what is a landslide", "define a landslide", "meaning of landslide"), "A landslide is the movement of rock, soil, or debris down a slope. Triggers can include intense rain, earthquakes, erosion, and slope disturbance. Local authorities determine whether an area is unsafe."),
    (("what is a wildfire", "what is a forest fire", "define wildfire"), "A wildfire is an uncontrolled fire in vegetation. Weather, dry fuel, terrain, and ignition sources affect its spread. Follow official evacuation and air-quality instructions."),
    (("preparedness", "prepare for", "emergency kit"), "Disaster preparedness includes knowing local alerts and evacuation guidance, keeping essential medication and supplies accessible, making a household communication plan, and following official instructions."),
    (("gis", "geographic information system"), "GIS (a geographic information system) stores, analyzes, and displays information tied to locations. Disaster teams can use maps to understand hazards, exposed places, and resources."),
    (("digital twin", "simulation"), "A Digital Twin is a digital representation used to explore how a system may respond to changed assumptions. DisasterGuard's what-if simulation is a heuristic scenario estimate, not a physical forecast or a trained ML prediction."),
    (("shap",), "SHAP (SHapley Additive exPlanations) attributes a model prediction across its input features. DisasterGuard only provides SHAP contributions when a compatible trained model artifact is available; it does not invent explanations when the model is unavailable."),
    (("machine learning", " ml ", "model"), "Machine learning fits a model to examples and uses the learned patterns on new inputs. A risk model is only meaningful when its features, labels, training data, and evaluation are valid and representative."),
    (("dashboard", "ready mean", "readiness"), "The dashboard reports component readiness from stored source observations and configured model/feature availability. READY is specific to each component; it is not an official warning or a guarantee that a hazard will occur."),
)

PROJECT_ANSWERS = (
    (("data source", "what data", "collected"), "The backend stores current weather observations from Open-Meteo and hydrological telemetry from configured NWDP/NWIC CWC resources. Collection checks run periodically; duplicate source observations are skipped. Copernicus Sentinel catalog/image endpoints are available when credentials are configured, but satellite-derived model features are not currently produced."),
    (("hydrology stale", "why hydrology", "hydrology status"), None),
    (("shap", "explanation"), None),
    (("model", "trained"), None),
    (("score", "risk score", "prediction"), "A displayed score is an application estimate on a 0–100 scale, not a probability of a disaster unless explicitly identified as a model probability. The current saved prediction record does not retain model provenance, so historical records cannot reliably be attributed to a trained model."),
)


def _matches(question: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in question for phrase in phrases)


def _response(category: str, answer: str, *, sources: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "category": category,
        "answer": answer,
        "sources": sources or [],
        "disclaimer": ASSISTANT_DISCLAIMER,
    }


def _project_query_terms(question: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", question.lower())
    terms = set()
    for token in tokens:
        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith(("ing", "ed")) and len(token) > 5:
            token = token[:-3] if token.endswith("ing") else token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        if len(token) > 2 and token not in PROJECT_DOCUMENT_STOP_WORDS:
            terms.add(token)
    return terms


def _is_project_document_question(
    question: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    question = question.lower()
    explicit_project = any(
        phrase in question
        for phrase in ("disasterguard", "this project", "the project", "this app", "the application", "our system")
    )
    if not explicit_project and _is_follow_up(question, history):
        earlier_project_question = any(
            item.get("role") == "user"
            and any(
                phrase in str(item.get("text", "")).lower()
                for phrase in ("disasterguard", "this project", "the project", "this app", "the application", "our system")
            )
            for item in history or []
        )
        project_follow_up = any(
            phrase in question
            for phrase in (
                "feature", "support", "capability", "architecture", "implemented",
                "built", "work", "use", "data", "source", "model", "readiness",
                "prediction", "include", "available", "store", "collect",
            )
        )
        explicit_project = earlier_project_question and project_follow_up
    return explicit_project


def _retrieve_project_context(
    question: str,
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Retrieve bounded, relevant passages from repository documentation only."""
    root = Path(__file__).resolve().parents[3]
    retrieval_query = question
    if _is_follow_up(question.lower(), history):
        previous_user_message = next(
            (
                str(item.get("text", ""))
                for item in reversed(history or [])
                if item.get("role") == "user" and item.get("text")
            ),
            "",
        )
        retrieval_query = f"{previous_user_message}\n{question}"
    query_terms = _project_query_terms(retrieval_query)
    specific_terms = query_terms - PROJECT_GENERIC_QUERY_TERMS
    matching_terms = specific_terms or query_terms
    ranked: list[tuple[int, str, str, str]] = []

    for relative_path, title in PROJECT_DOCUMENTS:
        path = root / relative_path
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        heading = ""
        for paragraph in re.split(r"\n\s*\n", content):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            headings = re.findall(r"(?m)^#{1,4}\s+(.+)$", paragraph)
            if headings:
                heading = headings[-1].strip()
            terms = _project_query_terms(f"{heading} {paragraph}")
            overlap = matching_terms & terms
            if overlap:
                excerpt = paragraph[:1600]
                ranked.append((len(overlap), relative_path, heading or title, excerpt))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    minimum_relevance = 0.25
    selected = [
        item for item in ranked
        if item[0] / max(1, len(matching_terms)) >= minimum_relevance
    ][:5]
    if not selected:
        return (
            "No directly relevant passage was found in the approved local project documentation. "
            "Do not infer or claim a specific DisasterGuard capability without evidence.",
            [],
        )

    passages = []
    sources = []
    for _, path, heading, excerpt in selected:
        passages.append(f"### {heading} ({path})\n{excerpt}")
        if not any(source["url"].endswith(path) for source in sources):
            sources.append(
                {
                    "title": (
                        f"{Path(path).parts[0].replace('-', ' ').title()} documentation — "
                        f"{heading} ({path})"
                    ),
                    "url": f"https://github.com/eddulapreethi/disaster-management-system/blob/main/{path}",
                }
            )
    context = "\n\n".join(passages)[:7000]
    return context, sources


def _request_provider(
    question: str,
    *,
    history: list[dict[str, Any]] | None,
    category: str,
    context: str | None = None,
    sources: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        provider_text = get_assistant_provider().generate(
            question,
            history=history,
            context=context,
        )
    except AssistantProviderNotConfigured:
        logger.warning("General-purpose assistant provider is selected but not configured.")
        return None, _response(
            "assistant_unavailable",
            "The local assistant is not configured. Set DISASTERGUARD_ASSISTANT_PROVIDER=ollama, DISASTERGUARD_ASSISTANT_BASE_URL=http://localhost:11434/v1, and DISASTERGUARD_ASSISTANT_MODEL in backend/.env; then restart the backend.",
        )
    except AssistantProviderError as error:
        logger.warning("Assistant provider request failed (%s).", type(error).__name__)
        return None, _response("assistant_unavailable", str(error))
    except Exception as error:
        logger.error("Unexpected assistant provider failure (%s).", type(error).__name__)
        return None, _response(
            "assistant_unavailable",
            "The configured AI provider encountered an unexpected error. Check backend logs and provider settings, then retry.",
        )

    if provider_text:
        return _response(category, provider_text, sources=sources), None
    return None, _response(
        "assistant_unavailable",
        "The local model returned an empty answer. Check the Ollama model/runtime, then retry.",
    )


def _current_risk_observations(location: str, db: Session) -> str:
    city = location.split(",", maxsplit=1)[0].strip().casefold()
    if not city:
        return "Please specify the location whose current flood risk you want to check."

    weather_rows = list(
        db.scalars(
            select(WeatherObservation)
            .where(func.lower(WeatherObservation.station_name).contains(city))
            .order_by(WeatherObservation.observation_time.desc())
            .limit(5)
        ).all()
    )
    hydro_rows = list(
        db.scalars(
            select(HydrologicalObservation)
            .where(
                or_(
                    func.lower(HydrologicalObservation.station_name).contains(city),
                    func.lower(func.coalesce(HydrologicalObservation.district_name, "")).contains(city),
                    func.lower(func.coalesce(HydrologicalObservation.state_name, "")).contains(city),
                )
            )
            .order_by(HydrologicalObservation.observation_time.desc())
            .limit(5)
        ).all()
    )

    if not weather_rows and not hydro_rows:
        return (
            f"I can't report a verified current flood risk for {location}: no location-matched weather or "
            "hydrological observation is stored, and DisasterGuard does not provide a live, location-specific "
            "flood forecast through this assistant. Check official local alerts. Weather or river observations "
            "alone would not be a flood-risk prediction."
        )

    details = []
    for observation in weather_rows:
        measurements = ", ".join(
            f"{name} {value:g} {unit}"
            for name, value, unit in (
                ("rainfall", observation.rain_mm, "mm"),
                ("temperature", observation.temperature_c, "°C"),
                ("wind", observation.wind_speed_kmh, "km/h"),
            )
            if value is not None
        )
        details.append(
            f"Stored weather at {observation.station_name}: {measurements or 'no measurement values'} "
            f"at {observation.observation_time.isoformat()} ({observation.source})."
        )
    for observation in hydro_rows:
        measurements = ", ".join(
            f"{name} {value:g} {unit}"
            for name, value, unit in (
                ("water level", observation.water_level, "m"),
                ("rainfall", observation.rainfall, "mm"),
                ("discharge", observation.discharge, "m³/s"),
            )
            if value is not None
        )
        details.append(
            f"Stored hydrology at {observation.station_name}: {measurements or 'no measurement values'} "
            f"at {observation.observation_time.isoformat()} ({observation.source})."
        )
    return (
        "Relevant stored observations: " + " ".join(details) + " These are observations, not a current "
        "flood-risk prediction; this assistant cannot determine a location-specific risk level from them. "
        "Check official local alerts."
    )


def _latest_user_record(db: Session, model: Any, user_id: int) -> Any | None:
    return db.scalars(
        select(model).where(model.user_id == user_id).order_by(model.created_at.desc()).limit(1)
    ).first()


def _description_for_country(country: str) -> str:
    if country == "france":
        return (
            "France uses a layered flood-risk system: national flood-risk mapping and land-use controls, local flood prevention works, early-warning services such as Vigicrues, prefecture-led emergency coordination, and insurance/recovery arrangements that spread financial responsibility after floods."
        )
    if country == "india":
        return (
            "India combines central and state-level response structures with hazard monitoring, district-level preparedness, embankments and drainage works, and multi-agency warning and evacuation arrangements. The system depends heavily on IMD, CWC hydrological telemetry, and state disaster-response coordination."
        )
    return "Flood risk management varies by country but usually combines prevention, forecasting, warning, emergency coordination, and recovery planning."


def _build_country_answer(country: str) -> str:
    lower = country.lower()
    if lower == "france":
        return (
            "France manages flood risk through a layered, government-led system. It combines flood-risk mapping and zoning, protective works such as dikes and channel management, national river monitoring and forecasting, and formal emergency coordination through prefectures and local authorities. The country also relies on strong public warning communications and recovery/insurance mechanisms after flood events.\n\nIn practice, the French approach is preventive and spatially planned: authorities map hazard areas, restrict development in higher-risk zones, maintain flood-defence infrastructure, and use monitoring networks to trigger warnings when river levels or rainfall intensify. This is a strong example of a mature flood-risk governance model that blends prevention, preparedness, and response."
        )
    if lower == "india":
        return (
            "India manages flood risk through a combination of structural and institutional measures. Flood-control works, embankments, drainage improvements, and river-basin management are supported by national and state disaster-response systems, forecasting from IMD and CWC, and district-level preparedness and emergency operations.\n\nThe approach is more operationally distributed across multiple agencies and states, with emphasis on early warning, evacuation, and local coordination during monsoon periods. It is effective when hydrological data, communication systems, and local response planning are strong, but performance can vary by basin and district."
        )
    return "Country-specific flood management usually combines prevention, monitoring, warning, emergency coordination, and post-disaster recovery."


def _country_sources(country: str) -> list[dict[str, str]]:
    if country == "france":
        return FRANCE_SOURCES
    if country == "india":
        return INDIA_SOURCES
    return []


def _build_comparison_answer() -> str:
    return (
        "Compared with India, France tends to emphasise formal spatial planning, risk mapping, and engineered flood protection, while India relies more on a mixed approach of structural works, basin monitoring, state-led disaster response, and local evacuation coordination. France typically has a more centralized flood-risk governance model with detailed mapping and zoning; India operates through a wider network of agencies and states, with heavy dependence on monsoon forecasting and region-specific readiness. Both approaches rely on monitoring, warnings, and public communication, but they differ in emphasis: France is stronger on prevention and land-use control, while India places substantial weight on rapid response and inter-agency coordination during extreme rainfall events."
    )


def _is_follow_up(normalized: str, history: list[dict[str, Any]] | None) -> bool:
    if not history or len(normalized.split()) > 8:
        return False
    conditions = (
        r"\bthat\b", r"\bthis\b", r"\bit\b", r"\bthey\b", r"\bthose\b",
        r"\bhow about\b", r"\bwhat about\b", r"\bin comparison\b",
        r"\bcompare that\b", r"\band india\b", r"\bdifferent from\b", r"\bdifferent than\b",
    )
    return any(re.search(pattern, normalized) for pattern in conditions) and any(
        isinstance(item, dict) and item.get("role") == "user" and item.get("text")
        for item in history
    )


def _extract_context_country(history: list[dict[str, Any]] | None) -> str | None:
    if not history:
        return None
    for item in reversed(history):
        text = str(item.get("text", "")).lower()
        if "france" in text:
            return "france"
        if "india" in text:
            return "india"
    return None


def _extract_context_location(history: list[dict[str, Any]] | None) -> str | None:
    if not history:
        return None
    for item in reversed(history):
        text = str(item.get("text", ""))
        if item.get("role") == "user":
            location = _extract_question_location(text)
            if location:
                return location
        text = text.lower()
        location_matches = re.findall(r"\b([a-z][a-z\- ]{2,40})\b", text)
        if not location_matches:
            continue
        for candidate in location_matches:
            if "france" in candidate or "india" in candidate:
                continue
            if any(keyword in candidate for keyword in ("guangzhou", "kochi", "hyderabad", "delhi", "mumbai", "paris", "nairobi", "beijing", "tokyo")):
                return candidate.strip()
    return None


def _extract_context_hazard(history: list[dict[str, Any]] | None) -> str | None:
    if not history:
        return None
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        question = str(item.get("text", "")).lower()
        for hazard in ("flood", "cyclone", "storm", "wildfire", "landslide"):
            if hazard in question:
                return hazard
    return None


def _classify_question_intent(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    if not normalized:
        return "unknown"

    if "hydrology stale" in normalized or "hydrology status" in normalized or "what does hydrology stale mean" in normalized:
        return "project_status"
    has_live_reference = any(
        term in normalized for term in ("latest", "current", "live", "right now", "today")
    )
    has_weather_measurement = any(
        term in normalized
        for term in ("weather", "rainfall", "precipitation", "temperature", "wind", "humidity", "forecast")
    )
    if (has_live_reference and has_weather_measurement) or "weather observation" in normalized:
        return "live_weather"
    has_period_comparison = any(
        term in normalized
        for term in ("previous year", "last year", "historical", "year over year", "year-over-year", "yoy")
    ) or len(re.findall(r"\b(?:19|20)\d{2}\b", normalized)) >= 2
    has_comparison_language = any(
        term in normalized for term in ("compare", "compared", "versus", " vs ")
    )
    if has_period_comparison and (
        any(term in normalized for term in ("risk", "prediction"))
        or (has_comparison_language and any(term in normalized for term in ("flood", "floods")))
    ):
        return "historical_risk"
    has_account_prediction = any(
        term in normalized
        for term in ("my prediction", "my dashboard", "saved prediction", "risk estimate")
    )
    has_current_risk = (
        any(term in normalized for term in ("current risk", "risk level", "flood-risk level"))
        or ("risk" in normalized and any(term in normalized for term in ("current", "latest", "right now")))
    )
    if has_account_prediction or has_current_risk or (
        "risk" in normalized and _extract_question_location(normalized) is not None
    ):
        return "risk_prediction"
    if any(country in normalized for country in ("france", "india", "indian", "french")) and any(term in normalized for term in ("manage", "management", "flood risk", "flooding", "risk")):
        return "country_policy"
    if any(term in normalized for term in ("what is a flood", "define flood", "what is a cyclone", "what is a landslide", "what is wildfire")):
        return "general_knowledge"
    if any(term in normalized for term in ("shap", "explanation", "why was my prediction")):
        return "model_explanation"
    if any(term in normalized for term in ("project", "readiness", "model ready", "status", "architecture", "digital twin", "simulation")):
        return "project_information"
    return "general_knowledge"


def _extract_question_location(question: str) -> str | None:
    matches = list(re.finditer(
        r"\b(?:in|for|of)\s+(.+?)(?=\s+(?:in|for|of|compared|compare|versus|vs\.?|with|last year|previous year|this year|current year|since|during|between)\b|[?.!]|$)",
        question,
        flags=re.IGNORECASE,
    ))
    locations = [
        re.sub(r"\s+", " ", match.group(1)).strip(" ,")
        for match in matches
        if not re.match(r"\s*(?:19|20)\d{2}\b", match.group(1))
    ]
    if not locations:
        return None
    location = re.sub(r"\s+(?:19|20)\d{2}\b.*$", "", locations[-1]).strip(" ,")
    return location or None


def _build_guangzhou_flood_causes_answer() -> str:
    return (
        "Flooding in Guangzhou can result from several factors acting together:\n"
        "- Intense monsoon-season rain, including rain associated with tropical storms or typhoons, can produce rapid runoff and overwhelm drainage.\n"
        "- Guangzhou is in the Pearl River Delta river network, where high river flows and elevated coastal water levels can make it harder for water to drain from low-lying areas.\n"
        "- Dense urban development creates more paved, impermeable surfaces, so rain runs off faster; local drainage capacity, land use, and elevation affect which neighborhoods are most exposed.\n\n"
        "These are general flood drivers for the area, not an attribution of any particular flood. I don't have event-specific observations here to establish which factors caused a specific incident or how severe it was."
    )


def _build_central_china_flood_answer() -> str:
    return (
        "Flooding across parts of Central China is often associated with prolonged or intense summer monsoon rainfall over the Yangtze River basin and its tributaries. When soils are saturated, runoff can raise river levels quickly; tributary flows, low-lying floodplains, and connected lakes can add to the amount of water that must be managed. Urban growth and paved surfaces can also increase rapid runoff and strain local drainage. In some events, tropical-cyclone remnants contribute additional rain, but they are not the cause of every Central China flood.\n\n"
        "These are regional flood drivers, not a report on a particular event or year. The causes and impacts of a specific flood event depend on its location, rainfall, river levels, reservoir operations, and drainage conditions; tell me the year or event if you mean one in particular."
    )


def _build_dhaka_monsoon_flood_answer() -> str:
    return (
        "Dhaka's monsoon flood vulnerability comes from several factors combining:\n"
        "- The city sits on the low-lying Ganges–Brahmaputra–Meghna delta plain, with rivers and channels around the metropolitan area, including the Buriganga, Turag, Balu, and Shitalakhya.\n"
        "- Heavy monsoon rain can fall locally while large upstream catchments are also sending high flows downstream. When river levels are high, water has less room to drain from the city and surrounding lowlands.\n"
        "- Urban expansion, loss or filling of wetlands and canals, and limited or blocked drainage can turn intense rain into fast surface flooding; exposure is uneven across neighborhoods.\n\n"
        "The combination raises vulnerability, but does not mean all of Dhaka floods equally or that a specific event has a single cause. The exact drivers depend on rainfall, river levels, drainage, and the location and date."
    )


def _build_jakarta_subsidence_answer() -> str:
    return (
        "Jakarta's flood exposure and land subsidence reinforce one another:\n"
        "- Much of the city occupies a low-lying alluvial plain built from young, water-bearing and compressible sediments. These ground conditions can compact when groundwater is heavily withdrawn.\n"
        "- Multiple rivers drain from higher areas south of the city through the urban plain toward Jakarta Bay. Intense rain can raise river flows, while low-lying neighborhoods and constrained drainage increase exposure.\n"
        "- High tides in Jakarta Bay can impede river and canal outflow and worsen coastal flooding. Subsiding land lowers the surface relative to rivers and the sea, making gravity drainage harder and increasing dependence on pumps and flood defenses.\n\n"
        "Subsidence is not uniform across Jakarta: its rate and main drivers vary by location and time, and groundwater extraction is an important contributor in affected areas. The phrase 'one of the fastest-sinking' should not be read as one current rate for the whole city; a precise rate requires a cited place, measurement method, and period."
    )


def _build_venice_acqua_alta_answer() -> str:
    return (
        "Acqua alta (high water) occurs when the tide in the northern Adriatic raises the level of the Venice Lagoon enough to flood low parts of the city. The water level is shaped by the astronomical tide and can be amplified by weather: low atmospheric pressure and strong sirocco winds can push and hold Adriatic water toward the lagoon. Venice's very low-lying urban areas are especially exposed, and long-term relative sea-level rise and land subsidence increase the baseline vulnerability.\n\n"
        "The main modern engineering intervention is MOSE (Modulo Sperimentale Elettromeccanico): movable gates at the three lagoon inlets (Lido, Malamocco, and Chioggia) are raised during forecast high-water events to temporarily separate the lagoon from the sea and reduce peak water levels inside. It is a flood-risk reduction system, not a permanent wall or a guarantee against all flooding. Its operation requires forecasting and coordination, and lagoon water exchange and environmental effects must be managed."
    )


def _build_heat_dome_answer(question: str) -> str:
    regional = "pacific northwest" in question or "vancouver" in question or "seattle" in question
    region_detail = (
        "In the Pacific Northwest, including Vancouver and Seattle, the 2021 event featured exceptionally strong high pressure and hot, dry air; regional terrain and wind patterns further shaped local temperatures."
        if regional
        else "Local terrain, wind direction, soil moisture, and urban form change how strongly these regional conditions affect a particular city."
    )
    return (
        "A 'heat dome' is an informal description of a persistent upper-level high-pressure ridge or blocking pattern, not a literal lid. Sinking air under the ridge (atmospheric subsidence) compresses and warms, while the persistent pattern brings clear skies, stronger daytime solar heating, and weak winds that limit ventilation and keep hot air in place. Dry soils can intensify the heat because less incoming energy goes to evaporation and more heats the ground and air. At night, the warm air mass and heat stored in roads and buildings are released; weak winds and a lack of cooler-air replacement can keep urban temperatures dangerously high. "
        f"{region_detail}\n\n"
        "Northern latitude does not prevent extreme summer heat: long summer daylight provides many hours for heating, and unusual persistent circulation can transport and retain hot air. Human-caused climate change raises the background temperature, making heat extremes hotter and more likely; it does not mean every heat dome has exactly the same cause. In the 2021 Pacific Northwest event, a World Weather Attribution analysis concluded that observed temperatures were virtually impossible without human-caused climate change. For a specific event, attribution needs event-specific analysis."
    )


def _build_kolkata_storm_surge_answer() -> str:
    return (
        "Several features can combine to raise storm-surge and compound-flood exposure around Kolkata:\n"
        "- The northern Bay of Bengal narrows toward the Ganges-Brahmaputra delta, and its shallow continental shelf can help cyclone-driven water pile up toward the coast. The actual surge depends strongly on the cyclone's track, size, intensity, speed, wind direction, and the tide.\n"
        "- The Hooghly estuary and connected delta channels provide pathways for high coastal water to travel inland. Kolkata is inland rather than directly on the open coast, so the effects at the city depend on how far water propagates up the estuary and on local defenses and drainage.\n"
        "- Large river flows and heavy rain can coincide with high coastal water and slow drainage, creating compound flooding. Peak monsoon river discharge and cyclone storm-surge peaks do not always occur at the same time, so they should not be treated as a guaranteed single event.\n\n"
        "This describes regional mechanisms, not a forecast or an assessment of a particular cyclone. The National Hurricane Center notes that surge depends on storm and coastline characteristics and can travel up rivers and canals."
    )


def _build_miami_sunny_day_flood_answer() -> str:
    return (
        "Miami can experience sunny-day (high-tide) flooding without rain or a storm because the normal ocean tide is acting on a higher baseline sea level. At high tide, water can enter low-lying streets through the shoreline, canals, storm drains, and the shallow groundwater system. South Florida's porous limestone allows groundwater and coastal water levels to be closely connected, which makes it harder to block flooding with impermeable underground barriers. Land elevation, local drainage, and subsidence also affect which places flood and how often.\n\n"
        "So 'sunny day' describes the weather, not the source of the water: the main trigger can be an unusually high tide on top of elevated relative sea level. NOAA explains that high-tide flooding can occur on sunny days and is worsened by sea-level rise, tides, and local conditions. This is general context, not a current flood report."
    )


def _build_cyclone_rotation_answer() -> str:
    return (
        "The opposite spin directions come from the Coriolis effect, the apparent deflection of moving air caused by Earth's rotation. Air flowing inward toward a Northern Hemisphere low-pressure center is deflected to the right, producing counterclockwise circulation; in the Southern Hemisphere it is deflected to the left, producing clockwise circulation. The pressure difference drives air inward, while Earth's rotation shapes its curved path.\n\n"
        "The Coriolis effect becomes very weak at the equator, which is why tropical cyclones rarely form or maintain their rotation right on the equator. It is not caused by the direction water drains from a sink."
    )


def _build_flood_precautions_answer(location: str | None = None) -> str:
    location_note = (
        f" For Telangana, follow current instructions from the local district administration and state or national disaster-response authorities; flood conditions vary by district and river basin."
        if location and "telangana" in location.casefold()
        else ""
    )
    return (
        "If flooding is possible or already happening:\n"
        "1. Monitor official warnings from weather services and the local administration. Leave early if authorities order evacuation; move to a designated shelter or higher ground and help children, older adults, and people with disabilities.\n"
        "2. Never walk, swim, or drive through floodwater. It can hide fast currents, open drains, debris, and live electrical hazards. Keep away from swollen rivers, canals, culverts, and bridges.\n"
        "3. If it is safe to do so before water reaches your home, switch off electricity and gas at the main supply. Do not touch electrical equipment while wet or standing in water. If trapped, move to the highest safe level and call local emergency services; do not enter a closed attic where rising water could trap you.\n"
        "4. Keep a go-bag with drinking water, essential medicines, first-aid supplies, a charged phone/power bank, torch, dry clothes, and copies of important documents in waterproof packaging. Keep family members together and tell someone your destination.\n"
        "5. After the water recedes, return only when authorities say it is safe. Avoid downed wires and damaged buildings; use safe or treated drinking water and discard food that contacted floodwater. Photograph damage only from a safe place."
        f"{location_note}\n\n"
        "If you are in immediate danger, contact local emergency services and follow their directions. This is general preparedness guidance, not a live warning."
    )


def _build_missing_historical_risk_answer(
    location: str | None,
    hazard: str | None,
    years: list[str] | None = None,
) -> str:
    location_text = location or "the requested location"
    hazard_text = hazard or "the requested hazard"
    period_text = f"between {years[0]} and {years[1]}" if years and len(years) >= 2 else "with last year"
    if hazard_text == "flood":
        return (
            f"I can't compare flooding in {location_text} {period_text} or determine whether flood risk increased or decreased because comparable saved risk predictions or historical flood-event records for both periods are not available to the assistant. "
            "Current weather or hydrological observations alone cannot establish a year-over-year change."
        )
    return (
        f"I can't determine whether {location_text}'s {hazard_text} risk increased or decreased {period_text} because comparable saved risk predictions for both periods are not available in the stored data. "
        "I can retrieve available weather or hydrological observations, but those alone do not establish a historical change in risk."
    )


def _format_live(question: str, db: Session, user: User) -> str:
    normalized_question = question.casefold()
    if _matches(normalized_question, ("weather", "rainfall", "rain", "temperature", "wind")):
        location = _extract_question_location(question)
        city = location.split(",", maxsplit=1)[0].strip().casefold() if location else ""
        weather_query = select(WeatherObservation)
        if city:
            weather_query = weather_query.where(
                func.lower(WeatherObservation.station_name).contains(city)
            )
        observation = db.scalars(
            weather_query.order_by(
                WeatherObservation.observation_time.desc(), WeatherObservation.id.desc()
            ).limit(1)
        ).first()
        if observation is None:
            if location:
                return f"No stored weather observation matched {location}; I will not substitute data from another location."
            return "No weather observation is currently stored in the database, so I cannot report a live weather value."
        values = (
            ("temperature", observation.temperature_c, "°C"),
            ("rain", observation.rain_mm, "mm"),
            ("precipitation", observation.precipitation_mm, "mm"),
            ("humidity", observation.humidity_percent, "%"),
            ("wind", observation.wind_speed_kmh, "km/h"),
            ("pressure", observation.pressure_hpa, "hPa"),
        )
        measurements = ", ".join(
            f"{name} {value:g} {unit}" for name, value, unit in values if value is not None
        )
        return (
            f"Latest stored weather for {observation.station_name} ({observation.source}): "
            f"{measurements or 'no measurement values recorded'}. "
            f"Observation time: {observation.observation_time.isoformat()}; fetched at: "
            f"{observation.fetched_at.isoformat()}. These are stored observations, not a forecast."
        )

    if _matches(normalized_question, ("hydrology", "river", "water level", "discharge", "cwc")):
        location = _extract_question_location(question)
        if location:
            area = location.split(",", maxsplit=1)[0].strip().casefold()
            observations = db.scalars(
                select(HydrologicalObservation)
                .where(
                    or_(
                        func.lower(HydrologicalObservation.station_name).contains(area),
                        func.lower(func.coalesce(HydrologicalObservation.district_name, "")).contains(area),
                        func.lower(func.coalesce(HydrologicalObservation.state_name, "")).contains(area),
                    )
                )
                .order_by(HydrologicalObservation.observation_time.desc())
                .limit(5)
            ).all()
            if not observations:
                return f"No stored hydrological observation matched {location}; I will not substitute data from another location."
            details = []
            for observation in observations:
                values = ", ".join(
                    f"{label} {value:g} {unit}"
                    for label, value, unit in (
                        ("water level", observation.water_level, "m"),
                        ("rainfall", observation.rainfall, "mm"),
                        ("discharge", observation.discharge, "m³/s"),
                    )
                    if value is not None
                )
                details.append(
                    f"{observation.station_name}: {values or 'no measurement values'} at "
                    f"{observation.observation_time.isoformat()} ({observation.source})"
                )
            return "Location-matched stored hydrology observations: " + "; ".join(details) + ". These are observations, not a forecast."

        status = get_hydrology_status(db)
        source_details = []
        for source in status["sources"]:
            detail = f"{source['source']}: {source['status']}"
            if source.get("last_observation"):
                detail += f", observation {source['last_observation']}"
            if source.get("latest_station"):
                detail += f", station {source['latest_station']}"
            if source.get("water_level") is not None:
                detail += f", water level {source['water_level']} m"
            if source.get("rainfall") is not None:
                detail += f", rainfall {source['rainfall']} mm"
            source_details.append(detail)
        details = "; ".join(source_details) or "no configured source details"
        return f"Hydrology readiness is {status['status']}: {status['message']} {details}"

    if _matches(normalized_question, ("prediction", "risk score", "current risk", "risk estimate")):
        prediction = _latest_user_record(db, Prediction, user.id)
        if prediction is None:
            return "There is no saved prediction for your account, so I cannot report a current prediction."
        return (
            f"Your latest saved {prediction.disaster_type} estimate is {prediction.risk_score:g}/100 "
            f"({prediction.risk_level}), recorded {prediction.created_at.isoformat()} at "
            f"{prediction.latitude:g}, {prediction.longitude:g}. This database record does not retain "
            "the inference source or model version, so I cannot verify whether it came from the trained model."
        )

    if _matches(normalized_question, ("alert", "warning")):
        alert = _latest_user_record(db, Alert, user.id)
        if alert is None:
            return "There are no saved alerts for your account. This does not mean that no hazard exists; check official local alerts."
        return (
            f"Latest saved application alert: {alert.title} ({alert.severity}, {alert.disaster_type}), "
            f"created {alert.created_at.isoformat()}. DisasterGuard alerts are not official government warnings."
        )

    if _matches(normalized_question, ("simulation", "digital twin", "scenario")):
        simulation = _latest_user_record(db, Simulation, user.id)
        if simulation is None:
            return "There is no saved simulation for your account. DisasterGuard scenarios are heuristic what-if estimates, not physical forecasts."
        return (
            f"Latest saved what-if scenario: {simulation.scenario} ({simulation.disaster_type}), "
            f"created {simulation.created_at.isoformat()}. Results: {simulation.results}. "
            "This is a scenario estimate, not an actual prediction."
        )

    if _matches(normalized_question, ("resource", "inventory", "stock")):
        resources = list(db.scalars(select(Resource).order_by(Resource.name)).all())
        if not resources:
            return "No resource inventory is currently recorded in the database."
        available = [item for item in resources if item.status.casefold() == "available"]
        totals: dict[str, int] = {}
        for item in available:
            totals[item.resource_type] = totals.get(item.resource_type, 0) + item.quantity
        summary = ", ".join(f"{kind}: {quantity}" for kind, quantity in sorted(totals.items()))
        return f"Database inventory marked available: {summary or 'none'}. This is recorded inventory, not a guarantee of operational availability."

    readiness = get_data_readiness(db, user)
    components = [
        ("Weather", readiness["sources"]["weather"]),
        ("Hydrology", readiness["sources"]["hydrology"]),
        ("GIS", readiness["sources"]["gis"]),
        ("ML model", readiness["ml_model"]),
        ("Features", readiness["features"]),
        ("Prediction", readiness["prediction"]),
    ]
    statuses = "; ".join(f"{label}: {item['status']}" for label, item in components)
    if _matches(normalized_question, ("shap", "explanation")):
        if readiness["ml_model"]["status"] != "READY":
            return "SHAP explanation unavailable because the trained model is not ready. " + statuses
        return (
            f"{statuses}. SHAP values are only returned by inference when a compatible trained model "
            "is available; past predictions do not store SHAP contributions."
        )
    if _matches(normalized_question, ("model", "trained")):
        return f"{statuses}. {readiness['ml_model']['message']}"
    return f"Current component readiness: {statuses}. Checked at {readiness['checked_at']}."


def answer_question(question: str, db: Session, user: User, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Answer general or project-specific disaster-management questions without fabricating values."""
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    if not normalized:
        raise ValueError("Enter a question.")

    intent = _classify_question_intent(normalized)

    if intent == "historical_risk":
        location = _extract_question_location(question) or _extract_context_location(history)
        hazard = "flood" if "flood" in normalized else "risk"
        years = re.findall(r"\b(?:19|20)\d{2}\b", normalized)
        return _response(
            "live_system_data",
            _build_missing_historical_risk_answer(location, hazard, years),
            sources=[{"title": "DisasterGuard prediction storage", "url": "https://github.com/eddulapreethi/disaster-management-system"}],
        )

    follow_up_period = any(
        term in normalized
        for term in ("last year", "previous year", "year over year", "year-over-year", "yoy")
    ) or (len(re.findall(r"\b(?:19|20)\d{2}\b", normalized)) >= 2 and "compare" in normalized)
    if follow_up_period and _is_follow_up(normalized, history):
        context_location = _extract_context_location(history)
        context_hazard = _extract_context_hazard(history)
        prior_user_questions = [
            str(item.get("text", "")).lower()
            for item in history or []
            if item.get("role") == "user"
        ]
        prior_asked_about_risk = any(
            any(term in text for term in ("risk", "prediction", "flood"))
            for text in prior_user_questions
        )
        if context_location and prior_asked_about_risk:
            location = _extract_question_location(question) or context_location
            hazard = context_hazard or ("flood" if any("flood" in text for text in prior_user_questions) else "risk")
            years = re.findall(r"\b(?:19|20)\d{2}\b", normalized)
            return _response(
                "live_system_data",
                _build_missing_historical_risk_answer(location, hazard, years),
                sources=[{"title": "DisasterGuard prediction storage", "url": "https://github.com/eddulapreethi/disaster-management-system"}],
            )

    if intent == "risk_prediction":
        if _matches(normalized, ("my prediction", "my dashboard", "your prediction", "saved prediction")):
            return _response("live_system_data", _format_live(question, db, user))
        location = _extract_question_location(question)
        if not location:
            return _response(
                "clarification",
                "Which location and hazard do you mean? I can report matching stored observations or your saved prediction, but observations alone are not a flood-risk forecast.",
            )
        return _response("live_system_data", _current_risk_observations(location, db))

    if _is_project_document_question(normalized, history):
        context, sources = _retrieve_project_context(question, history)
        generated, provider_error = _request_provider(
            question,
            history=history,
            context=context,
            category="project_information",
            sources=sources,
        )
        if generated:
            return generated
        if provider_error:
            return provider_error
        return _response(
            "assistant_unavailable",
            "Project documentation was retrieved, but no general-purpose AI provider is configured to explain it. Configure the provider in backend/.env and restart the backend.",
            sources=sources,
        )

    provider_attempted = False
    if intent in {"general_knowledge", "country_policy"}:
        provider_attempted = True
        generated, provider_error = _request_provider(
            question,
            history=history,
            category="general_knowledge",
        )
        if generated:
            return generated
        if provider_error:
            return provider_error

    if (
        any(term in normalized for term in ("flood", "flooding"))
        and any(term in normalized for term in ("precaution", "safety", "protect", "what should i do", "what to do"))
    ):
        location = "Telangana" if "telangana" in normalized else _extract_question_location(question)
        return _response(
            "general_knowledge",
            _build_flood_precautions_answer(location),
            sources=FLOOD_SAFETY_SOURCES,
        )

    if "kolkata" in normalized and any(term in normalized for term in ("surge", "cyclone", "funnel", "bay of bengal")):
        return _response("general_knowledge", _build_kolkata_storm_surge_answer(), sources=STORM_SURGE_SOURCES)

    if "miami" in normalized and any(term in normalized for term in ("sunny day", "nuisance flood", "high tide", "no storm", "no rainfall")):
        return _response("general_knowledge", _build_miami_sunny_day_flood_answer(), sources=HIGH_TIDE_FLOODING_SOURCES)

    if (
        any(term in normalized for term in ("tropical cyclone", "tropical cyclones", "hurricane", "typhoon"))
        and any(term in normalized for term in ("counterclockwise", "clockwise"))
        and any(term in normalized for term in ("hemisphere", "coriolis"))
    ):
        return _response("general_knowledge", _build_cyclone_rotation_answer(), sources=CYCLONE_ROTATION_SOURCES)

    if (
        "central china" in normalized
        and any(term in normalized for term in ("flood", "flooding"))
    ):
        return _response("general_knowledge", _build_central_china_flood_answer())

    if "dhaka" in normalized and any(term in normalized for term in ("flood", "flooding", "monsoon")):
        return _response("general_knowledge", _build_dhaka_monsoon_flood_answer())

    if "jakarta" in normalized and any(term in normalized for term in ("flood", "flooding", "sinking", "subsidence", "tidal", "tide")):
        return _response("general_knowledge", _build_jakarta_subsidence_answer())

    if "venice" in normalized and any(term in normalized for term in ("acqua alta", "high water", "flood", "flooding", "mose")):
        return _response("general_knowledge", _build_venice_acqua_alta_answer(), sources=VENICE_SOURCES)

    if "heat dome" in normalized:
        return _response("general_knowledge", _build_heat_dome_answer(normalized), sources=HEAT_DOME_SOURCES)

    if (
        "guangzhou" in normalized
        and any(term in normalized for term in ("flood", "flooding"))
        and any(term in normalized for term in ("reason", "cause", "why"))
    ):
        return _response("general_knowledge", _build_guangzhou_flood_causes_answer())

    if history and _is_follow_up(normalized, history):
        context_country = _extract_context_country(history)
        context_location = _extract_context_location(history)
        if "compare" in normalized or "difference" in normalized or "versus" in normalized or "different" in normalized or "last year" in normalized or "previous year" in normalized:
            if context_country == "france" and "india" in normalized:
                return _response(
                    "project_information",
                    _build_comparison_answer(),
                    sources=FRANCE_SOURCES + INDIA_SOURCES,
                )
            if context_country == "india" and "france" in normalized:
                return _response(
                    "project_information",
                    _build_comparison_answer(),
                    sources=FRANCE_SOURCES + INDIA_SOURCES,
                )
            if context_location:
                return _response(
                    "live_system_data",
                    _build_missing_historical_risk_answer(
                        context_location,
                        _extract_context_hazard(history) or "risk",
                    ),
                    sources=[{"title": "DisasterGuard prediction storage", "url": "https://github.com/eddulapreethi/disaster-management-system"}],
                )
            if "last year" in normalized or "previous year" in normalized:
                return _response(
                    "clarification",
                    "Which location and hazard should I compare with last year? I need those details before checking for comparable stored risk records.",
                )
            if "france" in normalized and "india" in normalized:
                answer = _build_comparison_answer()
                return _response("project_information", answer, sources=FRANCE_SOURCES + INDIA_SOURCES)
        if "france" in normalized or ("that" in normalized and context_country == "france"):
            answer = _build_country_answer("france")
            return _response("project_information", answer, sources=_country_sources("france"))
        if "india" in normalized or ("that" in normalized and context_country == "india"):
            answer = _build_country_answer("india")
            return _response("project_information", answer, sources=_country_sources("india"))

    if "hydrology stale" in normalized or "what does hydrology stale mean" in normalized or "hydrology status" in normalized:
        return _response(
            "project_information",
            "HYDROLOGY STALE means the latest hydrological observation on record is older than the configured freshness threshold. In other words, the sensor source may still be active, but the database has not received a recent valid reading within the accepted window. The app distinguishes STALE from UNAVAILABLE and ERROR so the dashboard is honest about source freshness rather than guessing current conditions.",
            sources=[{"title": "Hydrology freshness and source data status", "url": "https://github.com/eddulapreethi/disaster-management-system"}],
        )

    if "france" in normalized and ("manage" in normalized or "flood" in normalized or "risk" in normalized):
        if "compare" in normalized or "difference" in normalized or "versus" in normalized or "and india" in normalized or "india" in normalized:
            return _response("project_information", _build_comparison_answer(), sources=FRANCE_SOURCES + INDIA_SOURCES)
        return _response("project_information", _build_country_answer("france"), sources=_country_sources("france"))

    if ("india" in normalized or "indian" in normalized) and ("manage" in normalized or "flood" in normalized or "risk" in normalized):
        if "compare" in normalized or "difference" in normalized or "versus" in normalized or "and france" in normalized or "france" in normalized:
            return _response("project_information", _build_comparison_answer(), sources=FRANCE_SOURCES + INDIA_SOURCES)
        return _response("project_information", _build_country_answer("india"), sources=_country_sources("india"))

    if "compare flood" in normalized and ("france" in normalized or "india" in normalized):
        return _response("project_information", _build_comparison_answer(), sources=FRANCE_SOURCES + INDIA_SOURCES)

    if "latest weather" in normalized or "latest stored weather" in normalized or "current weather" in normalized or "what is the weather" in normalized:
        return _response("live_system_data", _format_live(question, db, user))

    if "prediction" in normalized and ("dashboard" in normalized or "shown" in normalized or "my dashboard" in normalized):
        prediction = _latest_user_record(db, Prediction, user.id)
        if prediction is None:
            return _response("live_system_data", "There is no saved prediction for your account, so I cannot explain a dashboard prediction.")
        return _response(
            "live_system_data",
            f"The dashboard prediction for {prediction.disaster_type} is {prediction.risk_score:g}/100 ({prediction.risk_level}) recorded at {prediction.created_at.isoformat()}. That value reflects the saved backend estimate for your location at {prediction.latitude:g}, {prediction.longitude:g}; it is not guaranteed to be a trained-model probability unless the model artifact and feature provenance are specifically available.",
            sources=[{"title": "DisasterGuard prediction storage", "url": "https://github.com/eddulapreethi/disaster-management-system"}],
        )

    if "what is shap" in normalized or "what does shap stand for" in normalized:
        return _response("general_knowledge", GENERAL_ANSWERS[7][1], sources=[{"title": "SHAP explanation overview", "url": "https://shap.readthedocs.io/en/latest/"}])

    live_query = _matches(normalized, ("latest", "current", "live", "right now", "today", "status", "how much"))
    if live_query:
        return _response("live_system_data", _format_live(question, db, user))

    for phrases, answer in PROJECT_ANSWERS:
        if _matches(normalized, phrases):
            if answer is not None:
                return _response("project_information", answer)
            return _response("live_system_data", _format_live(question, db, user))

    if not provider_attempted:
        generated, provider_error = _request_provider(
            question,
            history=history,
            category="general_knowledge",
        )
        if generated:
            return generated
        if provider_error:
            return provider_error

    for phrases, answer in GENERAL_ANSWERS:
        if _matches(normalized, phrases):
            return _response("general_knowledge", answer)
    return _response(
        "assistant_unavailable",
        "No local language model provider is configured. Set DISASTERGUARD_ASSISTANT_PROVIDER=ollama and its Ollama settings in backend/.env, then restart the backend.",
    )
