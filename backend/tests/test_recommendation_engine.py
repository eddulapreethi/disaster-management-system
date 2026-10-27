import importlib

import pytest


recommendations = importlib.import_module("ai-assistant.recommendation_engine")


def test_low_weather_heuristic_recommendations_remain_general() -> None:
    result = recommendations.generate_recommendations(
        {
            "disaster_type": "flood",
            "risk_score": 20,
            "risk_band": "low",
            "model_source": "weather_heuristic",
        }
    )

    assert result["risk_band"] == "low"
    assert any("official" in action.lower() for action in result["recommendations"])
    assert "not an official warning" in result["disclaimer"]


def test_higher_risk_category_receives_more_precautionary_guidance() -> None:
    high_risk = recommendations.generate_recommendations(
        {"disaster_type": "flood", "risk_score": 85, "risk_band": "high"}
    )
    low_risk = recommendations.generate_recommendations(
        {"disaster_type": "flood", "risk_score": 10, "risk_band": "low"}
    )

    assert high_risk["recommendations"] != low_risk["recommendations"]
    assert any("evacuate" in action.lower() for action in high_risk["recommendations"])


def test_recommendations_reject_missing_or_invalid_prediction_evidence() -> None:
    with pytest.raises(ValueError, match="risk_score"):
        recommendations.generate_recommendations({"disaster_type": "flood"})
    with pytest.raises(ValueError, match="between 0 and 100"):
        recommendations.generate_recommendations(
            {"disaster_type": "storm", "risk_score": float("nan")}
        )
