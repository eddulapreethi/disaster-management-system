from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.historical_data import historical_analytics
from app.models.user import User


def test_historical_analytics_api_returns_computed_summary() -> None:
    expected = {
        "status": "READY",
        "summary": {"unique_event_ids": 12},
        "capabilities": {"historical_descriptive_analytics": "SUPPORTED"},
    }
    with patch("app.api.historical_data.get_historical_analytics", return_value=expected):
        response = historical_analytics(_user=User(name="Test", email="test@example.test", hashed_password="unused"))

    assert response == expected


def test_historical_analytics_api_surfaces_invalid_source_data() -> None:
    with patch(
        "app.api.historical_data.get_historical_analytics",
        side_effect=ValueError("dataset hash mismatch"),
    ), pytest.raises(HTTPException) as raised:
        historical_analytics(_user=User(name="Test", email="test@example.test", hashed_password="unused"))

    assert raised.value.status_code == 503
    assert "dataset hash mismatch" in raised.value.detail
