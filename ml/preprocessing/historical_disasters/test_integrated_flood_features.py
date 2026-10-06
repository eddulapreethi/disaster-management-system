import pandas as pd

from ml.preprocessing.flood_feature_integration import build_integrated_historical_flood_features


def test_build_integrated_historical_flood_features_returns_model_schema() -> None:
    frame = pd.DataFrame([
        {
            "DisNo.": "EM-001",
            "Disaster Type": "Flood",
            "Disaster Subtype": "Flash flood",
            "Country": "India",
            "Subregion": "South Asia",
            "Location": "Bengaluru",
            "Start Year": 2021,
            "Latitude": 12.9716,
            "Longitude": 77.5946,
            "Total Deaths": 10,
            "No. Affected": 2500,
            "Total Affected": 2500,
            "Total Damage ('000 US$)": 1500,
            "River Basin": "Cauvery",
        }
    ])

    integrated = build_integrated_historical_flood_features(frame)

    required_columns = [
        "MonsoonIntensity",
        "TopographyDrainage",
        "RiverManagement",
        "Deforestation",
        "Urbanization",
        "ClimateChange",
        "DamsQuality",
        "Siltation",
        "AgriculturalPractices",
        "Encroachments",
        "IneffectiveDisasterPreparedness",
        "DrainageSystems",
        "CoastalVulnerability",
        "Landslides",
        "Watersheds",
        "DeterioratingInfrastructure",
        "PopulationScore",
        "WetlandLoss",
        "InadequatePlanning",
        "PoliticalFactors",
        "FloodProbability",
    ]

    assert set(required_columns).issubset(integrated.columns)
    assert integrated["FloodProbability"].between(0, 1).all()
    assert integrated.shape[0] == 1
