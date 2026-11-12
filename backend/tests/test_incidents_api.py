from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.incidents import router
from app.database.connection import Base
from app.database.database import get_db
from app.models.disaster import Disaster
from app.models.disaster_review import DisasterReview
from app.models.user import User
from app.schemas.incident import IncidentCreate
from app.services.environmental_data_service import query_environmental_data
from app.utils.authentication import get_current_user


@pytest.fixture
def incident_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _client(db: Session, user: User | None = None) -> TestClient:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_db] = lambda: db
    if user is not None:
        application.dependency_overrides[get_current_user] = lambda: user
    return TestClient(application)


def _user(db: Session, email: str, role: str = "user") -> User:
    user = User(name=email.split("@")[0], email=email, hashed_password="unused", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _payload(**changes):
    payload = {
        "title": "Riverbank water report",
        "hazard_category": "flood",
        "description": "Water is reported above the usual riverbank level.",
        "latitude": 51.5072,
        "longitude": -0.1276,
        "incident_time": "2026-11-12T10:00:00Z",
        "incident_timezone": "UTC",
        "evidence_metadata": [{
            "file_name": "river-photo.jpg",
            "media_type": "image/jpeg",
            "size_bytes": 1250,
            "sha256": "a" * 64,
        }],
    }
    return {**payload, **changes}


def _create(client: TestClient, **changes):
    return client.post("/api/incidents", json=_payload(**changes))


def test_submission_requires_auth_and_records_owner_provenance_and_pending_status(incident_db) -> None:
    unauthenticated = _client(incident_db)
    assert _create(unauthenticated).status_code == 401

    reporter = _user(incident_db, "reporter@example.test")
    response = _create(_client(incident_db, reporter))

    assert response.status_code == 201
    record = response.json()
    assert record["hazard_category"] == "flood"
    assert record["status"] == "pending"
    assert record["reporter_id"] == reporter.id
    assert record["source"] == "community_report"
    assert record["provenance"]["submission_method"] == "authenticated_community_report"
    assert record["incident_time"] == "2026-11-12T10:00:00Z"
    assert record["submitted_at"].endswith("Z")
    assert record["evidence_metadata"][0]["file_name"] == "river-photo.jpg"


@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 90.0001},
        {"longitude": -180.0001},
        {"incident_time": "2026-11-12T10:00:00+00:00", "incident_timezone": "Asia/Kolkata"},
        {"incident_timezone": "Not/A_Timezone"},
        {"hazard_category": "volcano"},
        {"evidence_metadata": [{
            "file_name": "..\\private.jpg",
            "media_type": "image/jpeg",
            "size_bytes": 10,
        }]},
        {"evidence_metadata": [{
            "file_name": "photo.jpg",
            "media_type": "image/jpeg",
            "size_bytes": 10,
            "url": "https://example.test/private.jpg",
        }]},
    ],
)
def test_submission_rejects_invalid_coordinates_time_hazard_and_evidence(incident_db, changes) -> None:
    reporter = _user(incident_db, "validate@example.test")
    response = _create(_client(incident_db, reporter), **changes)
    assert response.status_code == 422


def test_incident_schema_rejects_non_finite_coordinates() -> None:
    payload = _payload(latitude=float("nan"))
    with pytest.raises(ValidationError):
        IncidentCreate.model_validate(payload)


def test_global_coordinate_boundaries_and_timezone_dst_validation(incident_db) -> None:
    reporter = _user(incident_db, "global@example.test")
    for latitude, longitude in ((90, 180), (-90, -180)):
        response = _create(
            _client(incident_db, reporter),
            latitude=latitude,
            longitude=longitude,
            incident_time="2026-01-01T00:00:00",
            incident_timezone="Pacific/Kiritimati",
            evidence_metadata=[],
        )
        assert response.status_code == 201
        assert response.json()["latitude"] == latitude
        assert response.json()["longitude"] == longitude

    ambiguous = _create(
        _client(incident_db, reporter),
        incident_time="2026-11-01T01:30:00",
        incident_timezone="America/New_York",
    )
    nonexistent = _create(
        _client(incident_db, reporter),
        incident_time="2026-03-08T02:30:00",
        incident_timezone="America/New_York",
    )
    assert ambiguous.status_code == 422
    assert nonexistent.status_code == 422


@pytest.mark.parametrize(
    "category",
    ["flood", "cyclone", "storm", "wildfire", "heatwave", "drought", "earthquake", "landslide", "other"],
)
def test_all_supported_hazard_categories_are_accepted(incident_db, category) -> None:
    reporter = _user(incident_db, f"{category}@example.org")
    response = _create(
        _client(incident_db, reporter),
        hazard_category=category,
        evidence_metadata=[],
    )
    assert response.status_code == 201
    assert response.json()["hazard_category"] == category


def test_reporter_ownership_private_details_and_edit_permissions(incident_db) -> None:
    reporter = _user(incident_db, "owner@example.test")
    other = _user(incident_db, "other@example.test")
    owner_client = _client(incident_db, reporter)
    other_client = _client(incident_db, other)
    incident_id = _create(owner_client).json()["id"]

    global_list = other_client.get("/api/incidents")
    assert global_list.status_code == 200
    public_report = global_list.json()["records"][0]
    assert "reporter_id" not in public_report
    assert "evidence_metadata" not in public_report
    assert "review_history" not in public_report
    assert public_report["can_view_private"] is False
    owner_report = owner_client.get("/api/incidents").json()["records"][0]
    assert owner_report["can_view_private"] is True

    assert other_client.get(f"/api/incidents/{incident_id}").status_code == 404
    assert other_client.patch(f"/api/incidents/{incident_id}", json={"title": "Changed title"}).status_code == 404
    assert owner_client.patch(
        f"/api/incidents/{incident_id}",
        json={"title": "Updated river report", "description": "Water remains above the reported riverbank."},
    ).status_code == 200


def test_reviewer_authorization_transitions_and_review_history(incident_db) -> None:
    reporter = _user(incident_db, "submitter@example.test")
    ordinary = _user(incident_db, "ordinary@example.test")
    reviewer = _user(incident_db, "reviewer@example.test", role="reviewer")
    incident_id = _create(_client(incident_db, reporter)).json()["id"]

    request = {"status": "verified"}
    assert _client(incident_db, ordinary).post(
        f"/api/incidents/{incident_id}/reviews",
        json=request,
    ).status_code == 403
    assert _client(incident_db, reviewer).post(
        f"/api/incidents/{incident_id}/reviews",
        json=request,
    ).status_code == 200
    assert _client(incident_db, reviewer).post(
        f"/api/incidents/{incident_id}/reviews",
        json=request,
    ).status_code == 409

    detail = _client(incident_db, reporter).get(f"/api/incidents/{incident_id}")
    assert detail.status_code == 200
    report = detail.json()
    assert report["status"] == "verified"
    assert report["review_history"] == [{
        "reviewer_id": reviewer.id,
        "reviewer_name": reviewer.name,
        "previous_status": "pending",
        "new_status": "verified",
        "note": None,
        "created_at": report["review_history"][0]["created_at"],
    }]
    assert report["review_history"][0]["created_at"].endswith("Z")
    assert _client(incident_db, reporter).patch(
        f"/api/incidents/{incident_id}",
        json={"title": "Changes after review are not allowed"},
    ).status_code == 403

    own_id = _create(_client(incident_db, reviewer), title="Reviewer-owned incident").json()["id"]
    self_review = _client(incident_db, reviewer).post(
        f"/api/incidents/{own_id}/reviews",
        json=request,
    )
    assert self_review.status_code == 403


def test_rejected_and_needs_review_decisions_require_notes_and_rejection_is_hidden(incident_db) -> None:
    reporter = _user(incident_db, "author@example.test")
    reviewer = _user(incident_db, "reviewer2@example.test", role="reviewer")
    other = _user(incident_db, "reader@example.test")
    reporter_client = _client(incident_db, reporter)
    reviewer_client = _client(incident_db, reviewer)
    other_client = _client(incident_db, other)
    incident_id = _create(reporter_client).json()["id"]

    assert reviewer_client.post(
        f"/api/incidents/{incident_id}/reviews",
        json={"status": "needs_review"},
    ).status_code == 422
    assert reviewer_client.post(
        f"/api/incidents/{incident_id}/reviews",
        json={"status": "rejected", "note": "Insufficient incident detail."},
    ).status_code == 200
    assert other_client.get("/api/incidents?verification_status=rejected").json()["records"] == []
    own = reporter_client.get(f"/api/incidents/{incident_id}")
    assert own.json()["status"] == "rejected"


def test_filters_pagination_antimeridian_and_analytics(incident_db) -> None:
    reporter = _user(incident_db, "analytics@example.test")
    client = _client(incident_db, reporter)
    for title, category, longitude, incident_time in (
        ("Dateline east report", "earthquake", 179.5, "2026-11-10T12:00:00Z"),
        ("Dateline west report", "earthquake", -179.5, "2026-11-11T12:00:00Z"),
        ("Outside bounds report", "storm", 0.0, "2026-11-12T12:00:00Z"),
    ):
        response = _create(
            client,
            title=title,
            hazard_category=category,
            latitude=0.0,
            longitude=longitude,
            incident_time=incident_time,
            evidence_metadata=[],
        )
        assert response.status_code == 201

    first_page = client.get(
        "/api/incidents",
        params={"hazard_category": "earthquake", "west": 170, "south": -10, "east": -170, "north": 10, "limit": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["pagination"]["returned_records"] == 1
    assert first_page.json()["pagination"]["total_matching_records"] == 2
    assert first_page.json()["has_more"] is True
    second_page = client.get(
        "/api/incidents",
        params={"hazard_category": "earthquake", "west": 170, "south": -10, "east": -170, "north": 10, "limit": 1, "offset": 1},
    )
    assert second_page.json()["records"][0]["id"] != first_page.json()["records"][0]["id"]

    analytics = client.get("/api/incidents/analytics").json()
    assert analytics["total_reports"] == 3
    assert {item["key"]: item["count"] for item in analytics["by_hazard"]} == {
        "earthquake": 2,
        "storm": 1,
    }
    assert {item["key"]: item["count"] for item in analytics["by_status"]} == {"pending": 3}
    assert analytics["records_without_verified_region"] == 3
    assert analytics["region_breakdown_status"] == "NOT_AVAILABLE"
    assert len(analytics["by_day"]) == 3

    date_filtered = client.get(
        "/api/incidents",
        params={
            "start_time": "2026-11-11T00:00:00Z",
            "end_time": "2026-11-11T23:59:59Z",
        },
    )
    assert date_filtered.status_code == 200
    assert date_filtered.json()["pagination"]["total_matching_records"] == 1
    trend = client.get(
        "/api/incidents/analytics",
        params={"start_time": "2026-11-11T00:00:00Z", "end_time": "2026-11-12T23:59:59Z"},
    ).json()
    assert trend["total_reports"] == 2
    assert sum(item["count"] for item in trend["by_day"]) == 2


def test_legacy_ownerless_rows_remain_private_and_excluded_from_analytics(incident_db) -> None:
    reporter = _user(incident_db, "legacy-check@example.test")
    incident_db.add(
        Disaster(
            name="Legacy report",
            disaster_type="flood",
            description="Unowned legacy row",
            latitude=9.9,
            longitude=76.2,
            status="reported",
            created_at=datetime.now(timezone.utc),
        )
    )
    incident_db.commit()
    client = _client(incident_db, reporter)

    assert client.get("/api/incidents").json()["records"] == []
    assert client.get("/api/incidents/analytics").json()["total_reports"] == 0

    row = incident_db.scalar(select(Disaster).where(Disaster.user_id.is_(None)))
    assert row is not None
    assert row.status == "reported"


def test_community_reports_are_not_mixed_into_environmental_observation_catalog(incident_db) -> None:
    reporter = _user(incident_db, "separate-catalog@example.org")
    response = _create(_client(incident_db, reporter))
    assert response.status_code == 201

    catalog = query_environmental_data(incident_db)
    assert all(record.category != "disaster_event_report" for record in catalog.records)
    report_status = next(source for source in catalog.sources if source.category == "disaster_event_report")
    assert report_status.status == "UNVERIFIED"
    assert report_status.matching_records == 0


def test_review_history_is_persisted_with_reviewer_identity(incident_db) -> None:
    reporter = _user(incident_db, "persist-reporter@example.test")
    reviewer = _user(incident_db, "persist-reviewer@example.test", role="reviewer")
    incident_id = _create(_client(incident_db, reporter)).json()["id"]
    response = _client(incident_db, reviewer).post(
        f"/api/incidents/{incident_id}/reviews",
        json={"status": "needs_review", "note": "Please verify the reported location."},
    )

    assert response.status_code == 200
    review = incident_db.scalar(select(DisasterReview).where(DisasterReview.disaster_id == incident_id))
    assert review is not None
    assert review.reviewer_id == reviewer.id
    assert review.previous_status == "pending"
    assert review.new_status == "needs_review"
