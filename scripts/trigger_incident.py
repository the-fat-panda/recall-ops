"""Fire concurrent health checks to demonstrate the real connection-pool incident."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import urlopen

BASE_URL = os.getenv("ORDERS_API_URL", "http://localhost:8080").rstrip("/")


def health(index: int) -> tuple[int, str]:
    try:
        with urlopen(f"{BASE_URL}/health", timeout=10) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def main() -> None:
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(health, range(3)))
    for index, (status, body) in enumerate(results, start=1):
        print(f"request {index}: HTTP {status} {body}")
    statuses = [status for status, _ in results]
    if 500 in statuses:
        print("Pool-exhaustion incident reproduced.")
    elif all(status == 200 for status in statuses):
        print("All requests healthy (expected after rollback, pool size 20).")
    else:
        print("Unexpected response mix; inspect the service logs.")


if __name__ == "__main__":
    main()
