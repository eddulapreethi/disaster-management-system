import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

_BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_BACKEND_ENV_FILE)

# An empty inherited variable should not mask a valid local backend setting.
for _key, _value in dotenv_values(_BACKEND_ENV_FILE).items():
    if _value and not os.environ.get(_key, "").strip():
        os.environ[_key] = _value