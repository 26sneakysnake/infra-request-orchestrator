"""Readiness probe for the local stack started by docker compose.

Polls every endpoint from the host until all of them answer or the timeout expires.
Usage: python -m stack.health [--timeout SECONDS]
"""

import argparse
import http.client
import ssl
import sys
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    url: str
    # vcsim serves a self-signed certificate; verification is skipped for that local simulator only.
    verify_tls: bool = True


ENDPOINTS: dict[str, Endpoint] = {
    "orchestration health": Endpoint("http://localhost:9600/actuator/health/readiness"),
    "rest api": Endpoint("http://localhost:8080/v2/topology"),
    "operate": Endpoint("http://localhost:8080/operate"),
    "tasklist": Endpoint("http://localhost:8080/tasklist"),
    "connectors": Endpoint("http://localhost:8086/actuator/health/readiness"),
    "vcsim": Endpoint("https://localhost:8989/about", verify_tls=False),
}


def probe(endpoint: Endpoint, timeout: float = 5.0) -> bool:
    """Return True when the endpoint answers with a 2xx or 3xx status."""
    context = None
    if not endpoint.verify_tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(endpoint.url, timeout=timeout, context=context) as response:
            return 200 <= response.status < 400
    except (OSError, http.client.HTTPException):
        # Covers refused connections, timeouts, TLS errors and HTTP error statuses (HTTPError).
        return False


def wait_for(
    endpoints: Mapping[str, Endpoint], timeout: float, interval: float = 2.0
) -> dict[str, bool]:
    """Probe the endpoints not yet ready until all are ready or the timeout expires."""
    status = dict.fromkeys(endpoints, False)
    deadline = time.monotonic() + timeout
    while True:
        for name, endpoint in endpoints.items():
            if not status[name]:
                status[name] = probe(endpoint)
        if all(status.values()) or time.monotonic() >= deadline:
            return status
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait until the local stack answers.")
    parser.add_argument("--timeout", type=float, default=300, help="seconds to wait (default: 300)")
    args = parser.parse_args(argv)

    print(f"Waiting up to {args.timeout:.0f} s for {len(ENDPOINTS)} endpoints...", flush=True)
    status = wait_for(ENDPOINTS, timeout=args.timeout)
    for name, ready in status.items():
        print(f"{'OK' if ready else 'KO'}  {name:<22} {ENDPOINTS[name].url}")
    return 0 if all(status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
