from __future__ import annotations

import time

import requests

import collector

MAX_CONNECT_SECONDS = 4
MAX_READ_SECONDS = 8

_original_get = requests.get


def guarded_get(url, *args, **kwargs):
    requested_timeout = kwargs.get("timeout")
    kwargs["timeout"] = (MAX_CONNECT_SECONDS, MAX_READ_SECONDS)
    started = time.perf_counter()
    try:
        response = _original_get(url, *args, **kwargs)
        elapsed = time.perf_counter() - started
        print(
            f"HTTP {response.status_code} {elapsed:.2f}s {url} "
            f"timeout_was={requested_timeout!r}",
            flush=True,
        )
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(
            f"HTTP ERROR {elapsed:.2f}s {url} {type(exc).__name__}: {exc} "
            f"timeout_was={requested_timeout!r}",
            flush=True,
        )
        raise


def main():
    # collector imports the same requests module, so replacing requests.get here
    # automatically protects every network call in the existing collector.
    requests.get = guarded_get
    started = time.perf_counter()
    try:
        collector.main()
    finally:
        print(f"COLLECTOR TOTAL {time.perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
