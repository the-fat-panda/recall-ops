"""Read the repository's static Phase 3 defaults from config/default.yaml."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def orders_api_url() -> str:
    """Return the Compose-network sandbox URL, overridable for local probes."""
    return os.getenv("ORDERS_API_URL", "http://orders-api:8080").rstrip("/")
