"""Cala reachability diagnosis for GET /api/health?cala=1.

Runs each network step on its own, every step capped at TIMEOUT_S, so a hang shows *where* it hangs:
DNS (getaddrinfo) -> TCP connect to port 443 -> TLS handshake -> one HTTP entity_search call.
Reports only booleans, timings, HTTP status and exception class names: never the key, headers or bodies.
The result is cached for CACHE_S so the public endpoint cannot be used to spend Cala calls.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Optional

from cala_client import MCP_URL
from settings import load_env

TIMEOUT_S = 3.0
CACHE_S = 30.0
HOST = urllib.parse.urlparse(MCP_URL).hostname

_lock = threading.Lock()
_last: tuple[float, Optional[dict]] = (0.0, None)
_dns_pool = ThreadPoolExecutor(2)       # getaddrinfo has no timeout of its own


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _err(e: BaseException) -> str:
    return "timeout" if isinstance(e, (socket.timeout, TimeoutError, FutureTimeout)) else type(e).__name__


def run() -> dict:
    load_env()
    key = os.environ.get("CALA_API_KEY")
    out = {"key_set": bool(key), "host": HOST, "dns_resolves": False, "dns_ms": None, "ipv4": None, "ipv6": None,
           "tcp_connect": False, "tcp_ms": None, "tls": False, "tls_ms": None,
           "reachable": False, "http_status": None, "ms": None, "error_type": None, "failed_step": None}

    t0 = time.perf_counter()
    try:
        infos = _dns_pool.submit(socket.getaddrinfo, HOST, 443, 0, socket.SOCK_STREAM).result(timeout=TIMEOUT_S)
        out["dns_resolves"], out["dns_ms"] = True, _ms(t0)
        v4 = [i[4][0] for i in infos if i[0] == socket.AF_INET]
        v6 = [i[4][0] for i in infos if i[0] == socket.AF_INET6 and not i[4][0].startswith("::ffff:")]
        out["ipv4"], out["ipv6"] = len(set(v4)), len(set(v6))
    except Exception as e:
        out.update(error_type=_err(e), failed_step="dns", dns_ms=_ms(t0))
        return out

    addr = (v4 or [i[4][0] for i in infos])[0]
    t0 = time.perf_counter()
    try:
        sock = socket.create_connection((addr, 443), timeout=TIMEOUT_S)
        out["tcp_connect"], out["tcp_ms"] = True, _ms(t0)
    except Exception as e:
        out.update(error_type=_err(e), failed_step="tcp", tcp_ms=_ms(t0))
        return out

    t0 = time.perf_counter()
    try:
        with ssl.create_default_context().wrap_socket(sock, server_hostname=HOST) as tls:
            tls.settimeout(TIMEOUT_S)
            out["tls"], out["tls_ms"] = True, _ms(t0)
    except Exception as e:
        sock.close()
        out.update(error_type=_err(e), failed_step="tls", tls_ms=_ms(t0))
        return out

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "entity_search",
                                  "arguments": {"name": "Lifeline Ventures", "entity_types": ["Organization"],
                                                "limit": 1}}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if key:
        headers["X-API-KEY"] = key
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(MCP_URL, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            resp.read(1)
            out.update(reachable=True, http_status=resp.status)
    except urllib.error.HTTPError as e:            # an HTTP answer, even 401/402/403/429, means Cala is reachable
        out.update(reachable=True, http_status=e.code, error_type="HTTPError", failed_step="http")
    except Exception as e:
        out.update(error_type=_err(e), failed_step="http")
    out["ms"] = _ms(t0)
    return out


def probe() -> dict:
    """The diagnosis, at most once per CACHE_S (concurrent callers share one run)."""
    global _last
    with _lock:
        t, res = _last
        if res is not None and time.time() - t < CACHE_S:
            return {**res, "cached": True}
        res = run()
        _last = (time.time(), res)
        return {**res, "cached": False}
