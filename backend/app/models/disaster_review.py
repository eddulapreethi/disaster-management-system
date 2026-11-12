from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class DisasterReview(Base):
    __tablename__ = "disaster_report_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    disaster_id: Mapped[int] = mapped_column(ForeignKey("disasters.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
