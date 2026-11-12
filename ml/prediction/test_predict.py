import os
from pathlib import Path
from unittest.mock import patch

from ml.prediction.predict import DEFAULT_MODEL_PATH, configured_model_path, get_model_readiness


def test_model_path_uses_documented_default_when_environment_is_unset() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert configured_model_path() == DEFAULT_MODEL_PATH


def test_model_path_uses_documented_default_when_environment_is_empty() -> None:
    with patch.dict(os.environ, {"DISASTERGUARD_MODEL_PATH": ""}, clear=True):
        assert configured_model_path() == DEFAULT_MODEL_PATH


def test_model_path_uses_explicit_custom_environment_value(tmp_path: Path) -> None:
    custom_path = tmp_path / "custom-model.joblib"
    with patch.dict(os.environ, {"DISASTERGUARD_MODEL_PATH": str(custom_path)}, clear=True):
        assert configured_model_path() == custom_path


def test_model_readiness_uses_current_configured_path_when_no_path_is_passed(tmp_path: Path) -> None:
    custom_path = tmp_path / "missing-custom-model.joblib"
    with patch.dict(os.environ, {"DISASTERGUARD_MODEL_PATH": str(custom_path)}, clear=True):
        readiness = get_model_readiness()

    assert readiness["status"] == "NOT_READY"
    assert str(custom_path) in readiness["message"]
