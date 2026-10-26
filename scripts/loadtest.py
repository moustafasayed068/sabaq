"""Open-loop load test for the signed-in athlete pages. Standard library only.

    python scripts/loadtest.py --base http://localhost:8000 --sessions loadtest-sessions.txt \
        --rate 50 --seconds 60

Requests start on a fixed schedule (`--rate` per second) whatever the server does, so a slow
server shows up as latency, not as a lower request rate. Each request picks a seeded athlete
and one of: plan page, a workout day, the check-in page. Prints p50/p95/p99 per page.
Seed the athletes first with `python manage.py loadtest_seed`.
"""

from __future__ import annotations

import argparse
import http.client
import random
import statistics
import threading
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SESSION_COOKIE = "sessionid"


def pages(day: str) -> list[tuple[str, str]]:
    return [("plan", "/plan/"), ("day", f"/plan/day/{day}/"), ("check-in", "/plan/check-in/")]


class Results:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, int] = defaultdict(int)

    def add(self, name: str, seconds: float, ok: bool) -> None:
        with self.lock:
            self.latency[name].append(seconds)
            if not ok:
                self.errors[name] += 1


_local = threading.local()


def _connection(base: urllib.parse.ParseResult) -> http.client.HTTPConnection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        cls = http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection
        conn = cls(base.netloc, timeout=30)
        _local.conn = conn
    return conn


def hit(base: urllib.parse.ParseResult, path: str, session: str, host: str) -> tuple[float, bool]:
    headers = {"Cookie": f"{SESSION_COOKIE}={session}", "Host": host, "Connection": "keep-alive"}
    started = time.perf_counter()
    try:
        conn = _connection(base)
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        response.read()
        ok = response.status in (200, 302)
    except (OSError, http.client.HTTPException):
        _local.conn = None
        ok = False
    return time.perf_counter() - started, ok


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--host", help="Host header (defaults to the base URL host)")
    parser.add_argument("--sessions", type=Path, default=Path("loadtest-sessions.txt"))
    parser.add_argument("--rate", type=float, default=50.0)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()

    base = urllib.parse.urlparse(args.base)
    host = args.host or base.netloc
    athletes = [line.split() for line in args.sessions.read_text().splitlines() if line.strip()]
    results = Results()
    total = int(args.rate * args.seconds)
    rng = random.Random(7)  # noqa: S311  # nosec B311 - choosing pages, not security

    def job(name: str, path: str, session: str) -> None:
        seconds, ok = hit(base, path, session, host)
        results.add(name, seconds, ok)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i in range(total):
            due = started + i / args.rate
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            session, day = rng.choice(athletes)
            name, path = rng.choice(pages(day))
            pool.submit(job, name, path, session)
    elapsed = time.perf_counter() - started

    print(f"{total} requests in {elapsed:.1f} s ({total / elapsed:.1f}/s)")
    print(f"{'page':<10}{'n':>6}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'errors':>8}")
    every: list[float] = []
    for name, values in sorted(results.latency.items()):
        every += values
        print(
            f"{name:<10}{len(values):>6}{pct(values, 50) * 1000:>9.0f}"
            f"{pct(values, 95) * 1000:>9.0f}{pct(values, 99) * 1000:>9.0f}"
            f"{results.errors[name]:>8}"
        )
    print(
        f"{'all':<10}{len(every):>6}{statistics.median(every) * 1000:>9.0f}"
        f"{pct(every, 95) * 1000:>9.0f}{pct(every, 99) * 1000:>9.0f}"
        f"{sum(results.errors.values()):>8}"
    )


if __name__ == "__main__":
    main()
