from app.services.prediction_service import get_recommendations


def recommend_actions(disaster_type: str, risk_level: str) -> list[str]:
    return get_recommendations(disaster_type, risk_level)