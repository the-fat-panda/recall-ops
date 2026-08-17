"""In-memory deployment state for the intentionally broken orders-api release."""

from __future__ import annotations

from threading import RLock

VERSION_POOL_SIZES = {"v2.8.1": (1, 1), "v2.8.0": (2, 20)}


class VersionState:
    """Store the active release version; process restarts reset to the bad version."""

    def __init__(self) -> None:
        self._current_version = "v2.8.1"
        self._lock = RLock()

    def current(self) -> tuple[str, int, int]:
        with self._lock:
            version = self._current_version
            min_size, max_size = VERSION_POOL_SIZES[version]
            return version, min_size, max_size

    def set_version(self, version: str) -> tuple[str, int, int]:
        if version not in VERSION_POOL_SIZES:
            raise ValueError(f"Unknown orders-api version: {version}")
        with self._lock:
            self._current_version = version
            min_size, max_size = VERSION_POOL_SIZES[version]
            return version, min_size, max_size


state = VersionState()
