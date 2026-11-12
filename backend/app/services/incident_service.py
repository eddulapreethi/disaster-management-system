from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.disaster import Disaster
from app.models.disaster_review import DisasterReview
from app.models.user import User
from app.schemas.incident import (
    IncidentAnalyticsRead,
    IncidentCount,
    IncidentCreate,
    IncidentDailyCount,
    IncidentDetailRead,
    IncidentListRead,
    IncidentPagination,
    IncidentRead,
    IncidentReviewCreate,
    IncidentReviewRead,
    IncidentUpdate,
)

EDITABLE_STATUSES = {"pending", "needs_review"}
PUBLIC_STATUSES = {"pending", "verified", "needs_review", "rejected"}
VALID_TRANSITIONS = {
    "pending": {"verified", "rejected", "needs_review"},
    "needs_review": {"verified", "rejected"},
}


def _storage_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _base_query():
    return select(Disaster).where(
        Disaster.user_id.is_not(None),
        Disaster.status.in_(PUBLIC_STATUSES),
    )


def _list_query(
    *,
    hazard_category: str | None,
    status: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    bbox: tuple[float, float, float, float] | None,
    user: User,
):
    query = _base_query()
    if hazard_category is not None:
        query = query.where(Disaster.disaster_type == hazard_category)
    if status is not None:
        query = query.where(Disaster.status == status)
    if not _is_reviewer(user):
        query = query.where(or_(Disaster.status != "rejected", Disaster.user_id == user.id))
    if start_time is not None:
        query = query.where(Disaster.incident_time >= _storage_time(start_time))
    if end_time is not None:
        query = query.where(Disaster.incident_time <= _storage_time(end_time))
    if bbox is not None:
        west, south, east, north = bbox
        query = query.where(Disaster.latitude.between(south, north))
        longitude_filter = (
            Disaster.longitude.between(west, east)
            if west <= east
            else or_(Disaster.longitude >= west, Disaster.longitude <= east)
        )
        query = query.where(longitude_filter)
    return query


def _is_reviewer(user: User) -> bool:
    return user.role == "reviewer"


def _read_record(report: Disaster, user: User) -> IncidentRead:
    is_owner = report.user_id == user.id
    reviewer = _is_reviewer(user)
    return IncidentRead(
        id=report.id,
        title=report.name,
        hazard_category=report.disaster_type,
        description=report.description,
        latitude=report.latitude,
        longitude=report.longitude,
        incident_time=report.incident_time,
        incident_timezone=report.incident_timezone,
        submitted_at=report.submitted_at or report.created_at,
        status=report.status,
        source=report.source,
        provenance={
            "source": report.source,
            "submission_method": "authenticated_community_report",
            **(report.source_metadata or {}),
        },
        can_edit=is_owner and report.status in EDITABLE_STATUSES,
        can_review=reviewer and not is_owner and report.status in VALID_TRANSITIONS,
        can_view_private=is_owner or reviewer,
    )


def create_incident(db: Session, user: User, data: IncidentCreate) -> IncidentDetailRead:
    submitted_at = datetime.now(timezone.utc)
    report = Disaster(
        name=data.title,
        disaster_type=data.hazard_category,
        description=data.description,
        latitude=data.latitude,
        longitude=data.longitude,
        status="pending",
        user_id=user.id,
        incident_time=data.incident_time,
        incident_timezone=data.incident_timezone,
        source="community_report",
        source_metadata={"submission_method": "authenticated_community_report"},
        evidence_metadata=[item.model_dump(mode="json") for item in data.evidence_metadata],
        submitted_at=submitted_at,
        created_at=submitted_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _detail_record(db, report, user)


def list_incidents(
    db: Session,
    user: User,
    *,
    hazard_category: str | None,
    status: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
    offset: int,
) -> IncidentListRead:
    query = _list_query(
        hazard_category=hazard_category,
        status=status,
        start_time=start_time,
        end_time=end_time,
        bbox=bbox,
        user=user,
    )
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = db.scalar(count_query) or 0
    reports = db.scalars(
        query.order_by(Disaster.incident_time.desc(), Disaster.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return IncidentListRead(
        records=[_read_record(report, user) for report in reports],
        pagination=IncidentPagination(
            limit=limit,
            offset=offset,
            returned_records=len(reports),
            total_matching_records=total,
        ),
        has_more=offset + len(reports) < total,
    )


def _detail_record(db: Session, report: Disaster, user: User) -> IncidentDetailRead:
    base = _read_record(report, user)
    reviews = db.execute(
        select(DisasterReview, User.name)
        .join(User, User.id == DisasterReview.reviewer_id)
        .where(DisasterReview.disaster_id == report.id)
        .order_by(DisasterReview.created_at.asc(), DisasterReview.id.asc())
    ).all()
    return IncidentDetailRead(
        **base.model_dump(),
        evidence_metadata=report.evidence_metadata or [],
        review_history=[
            IncidentReviewRead(
                reviewer_id=review.reviewer_id,
                reviewer_name=reviewer_name,
                previous_status=review.previous_status,
                new_status=review.new_status,
                note=review.note,
                created_at=review.created_at,
            )
            for review, reviewer_name in reviews
        ],
        reporter_id=report.user_id,
    )


def get_incident_detail(db: Session, user: User, incident_id: int) -> IncidentDetailRead:
    report = db.scalar(
        select(Disaster).where(
            Disaster.id == incident_id,
            Disaster.user_id.is_not(None),
        )
    )
    if report is None or (report.user_id != user.id and not _is_reviewer(user)):
        raise LookupError("Incident report not found.")
    return _detail_record(db, report, user)


def update_incident(
    db: Session,
    user: User,
    incident_id: int,
    data: IncidentUpdate,
) -> IncidentDetailRead:
    report = db.get(Disaster, incident_id)
    if report is None or report.user_id != user.id:
        raise LookupError("Incident report not found.")
    if report.status not in EDITABLE_STATUSES:
        raise PermissionError("This incident report can no longer be edited by its reporter.")

    changes: dict[str, Any] = data.model_dump(exclude_unset=True)
    non_nullable_fields = {"title", "description", "latitude", "longitude"}
    if any(field in changes and changes[field] is None for field in non_nullable_fields):
        raise ValueError("Editable text and coordinate fields cannot be null.")
    if "title" in changes:
        report.name = changes.pop("title")
    if "evidence_metadata" in changes and changes["evidence_metadata"] is not None:
        changes["evidence_metadata"] = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in changes["evidence_metadata"]
        ]
    for field, value in changes.items():
        setattr(report, field, value)
    db.commit()
    db.refresh(report)
    return _detail_record(db, report, user)


def review_incident(
    db: Session,
    reviewer: User,
    incident_id: int,
    data: IncidentReviewCreate,
) -> IncidentDetailRead:
    if not _is_reviewer(reviewer):
        raise PermissionError("Reviewer permission is required.")
    report = db.get(Disaster, incident_id)
    if report is None or report.user_id is None:
        raise LookupError("Incident report not found.")
    if report.user_id == reviewer.id:
        raise PermissionError("Reviewers cannot review their own incident reports.")
    if data.status not in VALID_TRANSITIONS.get(report.status, set()):
        raise ValueError(f"Cannot change incident status from {report.status} to {data.status}.")

    review = DisasterReview(
        disaster_id=report.id,
        reviewer_id=reviewer.id,
        previous_status=report.status,
        new_status=data.status,
        note=data.note,
    )
    report.status = data.status
    db.add(review)
    db.commit()
    db.refresh(report)
    return _detail_record(db, report, reviewer)


def incident_analytics(
    db: Session,
    *,
    start_time: datetime | None,
    end_time: datetime | None,
    hazard_category: str | None,
) -> IncidentAnalyticsRead:
    base = select(Disaster).where(
        Disaster.user_id.is_not(None),
        Disaster.incident_time.is_not(None),
    )
    if start_time is not None:
        base = base.where(Disaster.incident_time >= _storage_time(start_time))
    if end_time is not None:
        base = base.where(Disaster.incident_time <= _storage_time(end_time))
    if hazard_category is not None:
        base = base.where(Disaster.disaster_type == hazard_category)

    filtered = base.subquery()
    total = db.scalar(select(func.count()).select_from(filtered)) or 0
    hazard_rows = db.execute(
        select(filtered.c.disaster_type, func.count())
        .group_by(filtered.c.disaster_type)
        .order_by(filtered.c.disaster_type)
    ).all()
    status_rows = db.execute(
        select(filtered.c.status, func.count())
        .group_by(filtered.c.status)
        .order_by(filtered.c.status)
    ).all()
    daily_rows = db.execute(
        select(func.date(filtered.c.incident_time), func.count())
        .group_by(func.date(filtered.c.incident_time))
        .order_by(func.date(filtered.c.incident_time))
    ).all()
    return IncidentAnalyticsRead(
        total_reports=total,
        by_hazard=[IncidentCount(key=key, count=count) for key, count in hazard_rows],
        by_status=[IncidentCount(key=key, count=count) for key, count in status_rows],
        by_day=[IncidentDailyCount(date=str(day), count=count) for day, count in daily_rows],
        records_without_verified_region=total,
        region_breakdown_status="NOT_AVAILABLE",
        disclaimer=(
            "Descriptive counts of submitted community reports only. Geographic coordinates are recorded, "
            "but no verified country/administrative-area attribution is available. These counts are not "
            "official observations, warnings, risk scores, or forecasts."
        ),
    )
