from app.api.recommendations import RecommendationRequest, create_recommendations


def test_recommendations_without_prediction_are_explicitly_general() -> None:
    result = create_recommendations(RecommendationRequest())

    assert result["risk_score"] is None
    assert result["risk_band"] == "unknown"
    assert "no validated location-specific prediction" in result["summary"]
    assert "guidance based on a confirmed local hazard" in result["disclaimer"]
    assert result["recommendations"]
