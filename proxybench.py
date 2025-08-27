#!/usr/bin/env python3
# proxybench.py — CI-hardened proxy benchmarking with speed profiles and optional MEGA realism
#
# Features:
# - Merge + dedupe with optional cross-protocol collapse (socks5 > http > socks4)
# - Stage A: quick connectivity + tiny read, multi-URL fallback, quick retries
# - Stage B: capped single-stream throughput sample
# - Stage C (MEGA mode): multi-stream HTTPS sustained test to simulate MegaBasterd
# - SOCKS5 remote DNS (socks5h), browser-like headers, retries with jitter
# - HTTPS-proxy fallback for entries in http.txt (try http:// then https:// to the proxy)
# - CSV/TSV outputs (+ optional gzip), live tqdm progress bar, console summary
# - CI hardening: safer defaults, start pacing, optional IPv6 skip, latency skip
# - Speed profiles: fast | balanced | slow via SPEED_PROFILE
# - Optional streaming CSV writer to bound memory; optional SOCKS5→SOCKS4 downgrade
#
# Deps:
#   pip install "httpx[socks]" anyio tqdm
#
# Key envs (see defaults below):
#   SPEED_PROFILE, CROSS_PROTO_DEDUP, MEGA_MODE, MEGA_STREAMS, MEGA_BYTES_PER_STREAM,
#   WORKERS, EFFECTIVE_WORKERS, PER_HOST_LIMIT, MAX_STARTS_PER_SEC, SKIP_IPV6,
#   LATENCY_SKIP_MS, MAX_THR_BPS, TRY_SOCKS4_DOWNGRADE, HTTP2, NO_PROGRESS,
#   STREAM_CSV, CSV_GZIP
#
# Outputs:
#   Output/MBProxiesAll.txt (ranked), Output/MBProxies.txt (threshold/backfill),
#   Output/MBProxies.csv(.gz), Output/MBProxies.meta.tsv

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Union, Iterable
import ipaddress
import csv
import gzip
import heapq
import random
from statistics import median
from urllib.parse import quote

import httpx
from tqdm import tqdm

# ------------------------
# Config (env-overridable)
# ------------------------
INPUT_DIR = os.environ.get("INPUT_DIR", ".")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "Output")

INPUT_FILES = {
    "socks5": os.path.join(INPUT_DIR, "socks5.txt"),
    "http":   os.path.join(INPUT_DIR, "http.txt"),   # http + https mixed
    "socks4": os.path.join(INPUT_DIR, "socks4.txt"),
}

TEST_URL = os.environ.get("TEST_URL", "https://cachefly.cachefly.net/10mb.test")

CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "2.5"))
READ_TIMEOUT_S    = float(os.environ.get("READ_TIMEOUT_S", "3.0"))
A_SAMPLE_BYTES    = int(os.environ.get("A_SAMPLE_BYTES", "20480"))    # 20 KiB

B_SAMPLE_BYTES    = int(os.environ.get("B_SAMPLE_BYTES", "384000"))   # ~0.366 MiB
B_MAX_DURATION_S  = float(os.environ.get("B_MAX_DURATION_S", "3.0"))

WORKERS           = int(os.environ.get("WORKERS", "200"))
PER_HOST_LIMIT    = int(os.environ.get("PER_HOST_LIMIT", "24"))

THR_WEIGHT        = float(os.environ.get("THR_WEIGHT", "0.001"))
LAT_PENALTY       = float(os.environ.get("LAT_PENALTY", "0.25"))
ERR_PENALTY       = float(os.environ.get("ERR_PENALTY", "50.0"))

MIN_COUNT         = int(os.environ.get("MIN_COUNT", "75"))
SCORE_THRESHOLD   = float(os.environ.get("SCORE_THRESHOLD", "50.0"))

SHUFFLE_INPUT     = os.environ.get("SHUFFLE_INPUT", "1") == "1"
CROSS_PROTO_DEDUP = os.environ.get("CROSS_PROTO_DEDUP", "1") == "1"
SKIP_IPV6         = os.environ.get("SKIP_IPV6", "0") == "1"

CSV_NAME          = os.environ.get("CSV_NAME", "MBProxies.csv")
TSV_NAME          = os.environ.get("TSV_NAME", "MBProxies.meta.tsv")
CSV_GZIP          = os.environ.get("CSV_GZIP", "0") == "1"

# Retry & jitter
A_RETRIES      = int(os.environ.get("A_RETRIES", "1"))
B_RETRIES      = int(os.environ.get("B_RETRIES", "0"))
QUICK_FAIL_S   = float(os.environ.get("QUICK_FAIL_S", "0.6"))
JITTER_S       = float(os.environ.get("JITTER_S", "0.05"))
START_JITTER_S = float(os.environ.get("START_JITTER_S", "0.02"))

# Lightweight pacing
MAX_STARTS_PER_SEC = float(os.environ.get("MAX_STARTS_PER_SEC", "0"))  # 0 disables

# Optional latency-based skip of Stage B
LATENCY_SKIP_MS = float(os.environ.get("LATENCY_SKIP_MS", "900"))

# Score clipping
MAX_THR_BPS = float(os.environ.get("MAX_THR_BPS", "5e7"))  # 50 MB/s

# Protocol fallback
TRY_SOCKS4_DOWNGRADE = os.environ.get("TRY_SOCKS4_DOWNGRADE", "1") == "1"

# Progress tuning
NO_PROGRESS = os.environ.get("NO_PROGRESS", "0") == "1"

# HTTP/2 toggle
HTTP2 = os.environ.get("HTTP2", "0") == "1"

# Multi-target URL lists
def _parse_url_list(env_key: str, default: str) -> List[str]:
    return [u.strip() for u in os.environ.get(env_key, default).split(",") if u.strip()]

URLS_HTTP  = _parse_url_list(
    "URLS_HTTP",
    "http://speed.hetzner.de/10MB.bin,http://cachefly.cachefly.net/10mb.test"
)
URLS_HTTPS = _parse_url_list(
    "URLS_HTTPS",
    "https://cachefly.cachefly.net/10mb.test,https://speed.hetzner.de/10MB.bin"
)
URLS_SOCKS = _parse_url_list(
    "URLS_SOCKS",
    "https://cachefly.cachefly.net/10mb.test,https://speed.hetzner.de/10MB.bin,http://speed.hetzner.de/10MB.bin"
)

# MEGA mode (may be toggled by profile)
MEGA_MODE             = os.environ.get("MEGA_MODE", "0") == "1"
MEGA_STREAMS          = int(os.environ.get("MEGA_STREAMS", "2"))
MEGA_BYTES_PER_STREAM = int(os.environ.get("MEGA_BYTES_PER_STREAM", "2097152"))  # 2 MiB
MEGA_MAX_DURATION_S   = float(os.environ.get("MEGA_MAX_DURATION_S", "6.0"))
MEGA_URLS             = _parse_url_list(
    "MEGA_URLS",
    "https://cachefly.cachefly.net/10mb.test,https://speed.hetzner.de/10MB.bin"
)
MEGA_ONLY_HTTPS       = os.environ.get("MEGA_ONLY_HTTPS", "1") == "1"

# Effective workers (may be overridden by profile)
EFFECTIVE_WORKERS = int(os.environ.get(
    "EFFECTIVE_WORKERS",
    str(min(WORKERS, 200) if MEGA_MODE else WORKERS)
))

# ---- Speed profile (fast | balanced | slow) ----
SPEED_PROFILE = os.environ.get("SPEED_PROFILE", "fast").lower()

def _apply_speed_profile():
    def setdefault(name, value):
        if os.environ.get(name) is None:
            globals()[name] = value

    if SPEED_PROFILE == "fast":
        setdefault("WORKERS", 200)
        setdefault("EFFECTIVE_WORKERS", min(WORKERS, 200))
        setdefault("PER_HOST_LIMIT", 24)
        setdefault("A_SAMPLE_BYTES", 20_480)
        setdefault("B_SAMPLE_BYTES", 384_000)
        setdefault("B_MAX_DURATION_S", 3.0)
        setdefault("A_RETRIES", 1)
        setdefault("B_RETRIES", 0)
        setdefault("MEGA_MODE", False)
        setdefault("MEGA_STREAMS", 2)
        setdefault("MEGA_BYTES_PER_STREAM", 2_097_152)
        setdefault("MEGA_MAX_DURATION_S", 6.0)
        setdefault("MAX_STARTS_PER_SEC", 0.0)
    elif SPEED_PROFILE == "balanced":
        setdefault("WORKERS", 250)
        setdefault("EFFECTIVE_WORKERS", min(WORKERS, 220))
        setdefault("PER_HOST_LIMIT", 28)
        setdefault("A_SAMPLE_BYTES", 32_768)
        setdefault("B_SAMPLE_BYTES", 600_000)
        setdefault("B_MAX_DURATION_S", 4.0)
        setdefault("A_RETRIES", 1)
        setdefault("B_RETRIES", 0)
        setdefault("MEGA_MODE", True)
        setdefault("MEGA_STREAMS", 3)
        setdefault("MEGA_BYTES_PER_STREAM", 2_097_152)
        setdefault("MEGA_MAX_DURATION_S", 7.0)
        setdefault("MAX_STARTS_PER_SEC", 120.0)
    else:  # slow
        setdefault("WORKERS", 200)
        setdefault("EFFECTIVE_WORKERS", min(WORKERS, 180))
        setdefault("PER_HOST_LIMIT", 24)
        setdefault("A_SAMPLE_BYTES", 40_960)
        setdefault("B_SAMPLE_BYTES", 1_000_000)
        setdefault("B_MAX_DURATION_S", 6.0)
        setdefault("A_RETRIES", 2)
        setdefault("B_RETRIES", 1)
        setdefault("MEGA_MODE", True)
        setdefault("MEGA_STREAMS", 4)
        setdefault("MEGA_BYTES_PER_STREAM", 3_145_728)  # 3 MiB
        setdefault("MEGA_MAX_DURATION_S", 9.0)
        setdefault("MAX_STARTS_PER_SEC", 90.0)

_apply_speed_profile()
# Recompute EFFECTIVE_WORKERS if not explicitly set, after profile changes
if os.environ.get("EFFECTIVE_WORKERS") is None:
    EFFECTIVE_WORKERS = min(WORKERS, 200) if MEGA_MODE else WORKERS
# Cap connections when MEGA mode is on (each proxy may open multiple sockets)
if MEGA_MODE and os.environ.get("EFFECTIVE_WORKERS") is None:
    per_proxy = 1 + max(1, MEGA_STREAMS)
    EFFECTIVE_WORKERS = max(50, min(EFFECTIVE_WORKERS, int(0.9 * WORKERS / per_proxy) * per_proxy))

PROTO_PRIORITY = {"socks5": 3, "http": 2, "socks4": 1}

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "KHTML, like Gecko) Chrome/119.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

# ------------------------
# Helpers
# ------------------------

def parse_line(line: str) -> Optional[Tuple[str, int, Optional[str], Optional[str]]]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    user: Optional[str] = None
    pw: Optional[str] = None
    hostport = s
    if "@" in s:
        auth, hostport = s.rsplit("@", 1)
        if ":" in auth:
            user, pw = auth.split(":", 1)
        else:
            user, pw = auth, ""
    if hostport.startswith("["):
        try:
            right = hostport.index("]")
            host = hostport[1:right]
            if hostport[right+1:right+2] != ":":
                return None
            port = int(hostport[right+2:])
        except Exception:
            return None
    else:
        parts = hostport.split(":")
        if len(parts) != 2:
            return None
        host, port_s = parts
        try:
            port = int(port_s)
        except ValueError:
            return None
    if not (1 <= port <= 65535):
        return None
    try:
        ip_obj = ipaddress.ip_address(host)
        if SKIP_IPV6 and isinstance(ip_obj, ipaddress.IPv6Address):
            return None
    except Exception:
        if any(c.isspace() for c in host) or len(host) > 255:
            return None
    return host, port, user, pw

def load_and_dedupe() -> Union[
    Dict[Tuple[str, int], Tuple[str, Optional[str], Optional[str]]],
    Dict[Tuple[str, int, str], Tuple[Optional[str], Optional[str]]]
]:
    if CROSS_PROTO_DEDUP:
        merged: Dict[Tuple[str, int], Tuple[str, Optional[str], Optional[str]]] = {}
        for proto, path in INPUT_FILES.items():
            p = Path(path)
            if not p.exists(): continue
            seen_in_file = set()
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    rec = parse_line(line)
                    if not rec: continue
                    h, pt, user, pw = rec
                    hp = (h, pt)
                    if hp in seen_in_file:
                        continue
                    seen_in_file.add(hp)
                    if hp not in merged or PROTO_PRIORITY[proto] > PROTO_PRIORITY[ merged[hp][0] ]:
                        merged[hp] = (proto, user, pw)
        return merged
    else:
        merged3: Dict[Tuple[str, int, str], Tuple[Optional[str], Optional[str]]] = {}
        for proto, path in INPUT_FILES.items():
            p = Path(path)
            if not p.exists(): continue
            seen_in_file = set()
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    rec = parse_line(line)
                    if not rec: continue
                    h, pt, user, pw = rec
                    hp = (h, pt)
                    if hp in seen_in_file:
                        continue
                    seen_in_file.add(hp)
                    merged3[(h, pt, proto)] = (user, pw)
        return merged3

def proxy_url_candidates(proto: str, host: str, port: int, user: Optional[str], pw: Optional[str]) -> List[str]:
    auth = ""
    if user is not None:
        auth = f"{quote(user, safe='')}:{quote(pw or '', safe='')}@"
    if proto == "socks5":
        urls = [f"socks5h://{auth}{host}:{port}"]
        if TRY_SOCKS4_DOWNGRADE:
            urls.append(f"socks4://{auth}{host}:{port}")
        return urls
    if proto == "socks4":
        return [f"socks4://{auth}{host}:{port}"]
    # http list can contain HTTPS proxies; try both to the proxy
    return [f"http://{auth}{host}:{port}", f"https://{auth}{host}:{port}"]

def fmt_hostport(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"

def _is_https(u: str) -> bool:
    return u.lower().startswith("https://")

def candidate_urls_for(proto: str) -> List[str]:
    if proto in ("socks5", "socks4"):
        return URLS_SOCKS
    if proto == "http":
        return URLS_HTTPS + URLS_HTTP
    return [TEST_URL]

def mega_urls() -> List[str]:
    out = MEGA_URLS
    if MEGA_ONLY_HTTPS:
        out = [u for u in out if _is_https(u)]
    random.shuffle(out)
    return out

# ------------------------
# Start pacing
# ------------------------

class StartPacer:
    def __init__(self, rate_per_sec: float):
        self.rate = max(0.0, rate_per_sec)
        self._lock = asyncio.Lock()
        self._last = 0.0
    async def wait(self):
        if self.rate <= 0:
            return
        async with self._lock:
            now = time.perf_counter()
            interval = 1.0 / self.rate
            wait = max(0.0, (self._last + interval) - now)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = max(now, self._last + interval)

# ------------------------
# Benchmarking
# ------------------------

class BenchResult:
    __slots__ = ("host","port","proto","ok","latency_ms","thr_bps","score",
                 "mega_thr_bps","mega_ok_streams","mega_errors")
    def __init__(self, host, port, proto):
        self.host = host
        self.port = port
        self.proto = proto
        self.ok = False
        self.latency_ms: Optional[float] = None
        self.thr_bps: float = 0.0
        self.score: float = -1e9
        self.mega_thr_bps: float = 0.0
        self.mega_ok_streams: int = 0
        self.mega_errors: int = 0
    def calc_score(self):
        eff_thr = min(self.mega_thr_bps if (MEGA_MODE and self.mega_thr_bps > 0) else self.thr_bps, MAX_THR_BPS)
        if (MEGA_MODE and self.mega_thr_bps > 0 and self.latency_ms is not None):
            self.score = (eff_thr * THR_WEIGHT) - (self.latency_ms * LAT_PENALTY) - (self.mega_errors * ERR_PENALTY)
        elif self.latency_ms is None or eff_thr <= 0:
            self.score = -1e9
        else:
            self.score = (eff_thr * THR_WEIGHT) - (self.latency_ms * LAT_PENALTY)

async def stage_a_quick_check(client: httpx.AsyncClient, proxies: Iterable[str], proto: str):
    urls = candidate_urls_for(proto)
    for pxy in proxies:
        for url in urls:
            attempts = 1 + max(0, A_RETRIES)
            for attempt in range(attempts):
                t0 = time.perf_counter()
                try:
                    with httpx.Timeout(CONNECT_TIMEOUT_S + READ_TIMEOUT_S):
                        async with client.stream(
                            "GET", url,
                            headers=BROWSER_HEADERS,
                            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=CONNECT_TIMEOUT_S),
                            proxies=pxy
                        ) as resp:
                            if resp.status_code >= 400:
                                raise httpx.HTTPStatusError("bad status", request=resp.request, response=resp)
                            total = 0
                            async for chunk in resp.aiter_bytes():
                                total += len(chunk)
                                if total >= A_SAMPLE_BYTES:
                                    latency_ms = (time.perf_counter() - t0) * 1000.0
                                    return True, latency_ms, url, pxy
                except Exception:
                    dt = time.perf_counter() - t0
                    if attempt < attempts - 1 and dt <= QUICK_FAIL_S:
                        if JITTER_S > 0:
                            await asyncio.sleep(random.uniform(0, JITTER_S))
                        continue
    return False, None, None, None

async def stage_b_throughput(client: httpx.AsyncClient, proxy: str, url: str) -> float:
    attempts = 1 + max(0, B_RETRIES)
    for attempt in range(attempts):
        start = time.perf_counter()
        got = 0
        try:
            async with client.stream(
                "GET", url,
                headers=BROWSER_HEADERS,
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=B_MAX_DURATION_S + 0.5, write=CONNECT_TIMEOUT_S),
                proxies=proxy
            ) as resp:
                if resp.status_code >= 400:
                    raise httpx.HTTPStatusError("bad status", request=resp.request, response=resp)
                async for chunk in resp.aiter_bytes():
                    got += len(chunk)
                    if got >= B_SAMPLE_BYTES or (time.perf_counter() - start) >= B_MAX_DURATION_S:
                        break
        except Exception:
            if attempt < attempts - 1:
                continue
            return 0.0
        dur = max(1e-6, time.perf_counter() - start)
        return got / dur
    return 0.0

async def _mega_stream(client: httpx.AsyncClient, proxy: str, url: str) -> Tuple[int, bool]:
    start = time.perf_counter()
    got = 0
    try:
        async with client.stream(
            "GET", url,
            headers=BROWSER_HEADERS,
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=MEGA_MAX_DURATION_S + 1.0, write=CONNECT_TIMEOUT_S),
            proxies=proxy
        ) as resp:
            if resp.status_code >= 400:
                return 0, False
            async for chunk in resp.aiter_bytes():
                got += len(chunk)
                if got >= MEGA_BYTES_PER_STREAM or (time.perf_counter() - start) >= MEGA_MAX_DURATION_S:
                    break
        return got, True if got > 0 else False
    except Exception:
        return 0, False

async def stage_c_mega(client: httpx.AsyncClient, proxy: str, proto: str) -> Tuple[float, int, int]:
    urls = mega_urls()
    if not urls:
        return 0.0, 0, 0
    url = urls[0]
    start = time.perf_counter()
    tasks = [asyncio.create_task(_mega_stream(client, proxy, url)) for _ in range(max(1, MEGA_STREAMS))]
    results = await asyncio.gather(*tasks)
    dur = max(1e-6, time.perf_counter() - start)
    total_bytes = sum(b for b, ok in results)
    ok_streams = sum(1 for b, ok in results if ok)
    errors = len(results) - ok_streams
    return total_bytes / dur, ok_streams, errors

# Streaming CSV writer (optional)
async def csv_writer_task(q: "asyncio.Queue[Optional[List]]", path: Path, header: List[str], meta: str, gzip_enabled: bool):
    if gzip_enabled:
        f = gzip.open(path, "wt", newline="", encoding="utf-8")
    else:
        f = path.open("w", newline="", encoding="utf-8")
    try:
        f.write(meta + "\n")
        w = csv.writer(f); w.writerow(header)
        while True:
            row = await q.get()
            if row is None:
                q.task_done()
                break
            w.writerow(row)
            q.task_done()
    finally:
        f.close()

async def worker(queue: asyncio.Queue, results: List["BenchResult"], client: httpx.AsyncClient,
                 pbar: tqdm, pacer: StartPacer, csv_q: Optional[asyncio.Queue]):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        host, port, proto, user, pw = item

        # Gentle pacing + tiny jitter
        await pacer.wait()
        if START_JITTER_S > 0:
            await asyncio.sleep(random.uniform(0, START_JITTER_S))

        br = BenchResult(host, port, proto)
        candidates = proxy_url_candidates(proto, host, port, user, pw)

        ok, latency, url_used, pxy = await stage_a_quick_check(client, candidates, proto)
        if ok and latency is not None and url_used and pxy:
            br.latency_ms = latency

            thr = 0.0
            if latency <= LATENCY_SKIP_MS:
                thr = await stage_b_throughput(client, pxy, url_used)
            br.thr_bps = thr

            if MEGA_MODE and thr > 0 and (proto == "http" or proto in ("socks5", "socks4")):
                mega_thr, ok_streams, errs = await stage_c_mega(client, pxy, proto)
                br.mega_thr_bps = mega_thr
                br.mega_ok_streams = ok_streams
                br.mega_errors = errs

            if (MEGA_MODE and br.mega_thr_bps > 0) or (not MEGA_MODE and thr > 0):
                br.ok = True
                br.calc_score()
            else:
                br.calc_score()
        else:
            br.calc_score()

        results.append(br)
        if csv_q is not None:
            csv_q.put_nowait([
                br.host, br.port, br.proto, int(br.ok),
                0 if br.latency_ms is None else round(br.latency_ms, 3),
                round(br.thr_bps, 1),
                round(br.mega_thr_bps, 1),
                br.mega_ok_streams,
                br.mega_errors,
                round(br.score, 3),
            ])
        pbar.update(1)
        queue.task_done()

async def run_benchmark(proxies: List[Tuple[str,int,str,Optional[str],Optional[str]]]) -> List["BenchResult"]:
    results: List[BenchResult] = []
    limits = httpx.Limits(max_connections=EFFECTIVE_WORKERS, max_keepalive_connections=PER_HOST_LIMIT)
    async with httpx.AsyncClient(http2=HTTP2, limits=limits, verify=True, trust_env=False) as client:
        q: asyncio.Queue = asyncio.Queue()
        for host, port, proto, user, pw in proxies:
            q.put_nowait((host, port, proto, user, pw))
        for _ in range(EFFECTIVE_WORKERS):
            q.put_nowait(None)

        # Optional streaming CSV setup
        csv_q: Optional[asyncio.Queue] = None
        writer_task = None
        if os.environ.get("STREAM_CSV", "0") == "1":
            csv_q = asyncio.Queue()
            csv_path = Path(OUTPUT_DIR) / (CSV_NAME + (".gz" if CSV_GZIP else ""))
            meta = f"# profile={SPEED_PROFILE}, mega={int(MEGA_MODE)}, workers={WORKERS}, eff={EFFECTIVE_WORKERS}, http2={int(HTTP2)}"
            header = ["host","port","proto","ok","latency_ms","thr_bps","mega_thr_bps","mega_ok_streams","mega_errors","score"]
            writer_task = asyncio.create_task(csv_writer_task(csv_q, csv_path, header, meta, CSV_GZIP))

        pacer = StartPacer(MAX_STARTS_PER_SEC)
        with tqdm(total=len(proxies), desc="Benchmarking", unit="proxy",
                  smoothing=0.1, miniters=1, mininterval=0.2, disable=NO_PROGRESS) as pbar:
            tasks = [asyncio.create_task(worker(q, results, client, pbar, pacer, csv_q)) for _ in range(EFFECTIVE_WORKERS)]
            await q.join()
            for t in tasks:
                await t

        if csv_q is not None:
            await csv_q.put(None)
            await csv_q.join()
            if writer_task:
                await writer_task
    return results

# ------------------------
# Outputs and summary
# ------------------------

def write_outputs(results: List["BenchResult"], duration_s: float, total: int):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    good = [r for r in results if r.ok]
    good.sort(key=lambda r: r.score, reverse=True)

    # MBProxiesAll.txt
    all_path = Path(OUTPUT_DIR) / "MBProxiesAll.txt"
    with all_path.open("w", encoding="utf-8") as f:
        for r in good:
            f.write(f"{fmt_hostport(r.host, r.port)}\n")

    # MBProxies.txt (threshold then backfill)
    selected: List[BenchResult] = [r for r in good if r.score >= SCORE_THRESHOLD]
    if len(selected) < MIN_COUNT:
        ids = set((r.host, r.port) for r in selected)
        for r in good:
            if len(selected) >= MIN_COUNT:
                break
            key = (r.host, r.port)
            if r.score < SCORE_THRESHOLD and key not in ids:
                selected.append(r); ids.add(key)

    mb_path = Path(OUTPUT_DIR) / "MBProxies.txt"
    with mb_path.open("w", encoding="utf-8") as f:
        for r in selected[:MIN_COUNT]:
            f.write(f"{fmt_hostport(r.host, r.port)}\n")

    # CSV batch write unless streaming already did it
    if os.environ.get("STREAM_CSV", "0") != "1":
        csv_path = Path(OUTPUT_DIR) / (CSV_NAME + (".gz" if CSV_GZIP else ""))
        header = ["host","port","proto","ok","latency_ms","thr_bps","mega_thr_bps","mega_ok_streams","mega_errors","score"]
        meta = f"# profile={SPEED_PROFILE}, mega={int(MEGA_MODE)}, workers={WORKERS}, eff={EFFECTIVE_WORKERS}, http2={int(HTTP2)}"
        if CSV_GZIP:
            with gzip.open(csv_path, "wt", newline="", encoding="utf-8") as f:
                f.write(meta + "\n")
                w = csv.writer(f); w.writerow(header)
                for r in results:
                    w.writerow([
                        r.host, r.port, r.proto, int(r.ok),
                        0 if r.latency_ms is None else round(r.latency_ms, 3),
                        round(r.thr_bps, 1),
                        round(r.mega_thr_bps, 1),
                        r.mega_ok_streams,
                        r.mega_errors,
                        round(r.score, 3),
                    ])
        else:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                f.write(meta + "\n")
                w = csv.writer(f); w.writerow(header)
                for r in results:
                    w.writerow([
                        r.host, r.port, r.proto, int(r.ok),
                        0 if r.latency_ms is None else round(r.latency_ms, 3),
                        round(r.thr_bps, 1),
                        round(r.mega_thr_bps, 1),
                        r.mega_ok_streams,
                        r.mega_errors,
                        round(r.score, 3),
                    ])

    # TSV (debug/continuity)
    tsv_path = Path(OUTPUT_DIR) / TSV_NAME
    with tsv_path.open("w", encoding="utf-8") as f:
        f.write("host\tport\tproto\tok\tlatency_ms\tthr_bps\tmega_thr_bps\tmega_ok_streams\tmega_errors\tscore\n")
        for r in results:
            f.write(f"{r.host}\t{r.port}\t{r.proto}\t{int(r.ok)}\t"
                    f"{0 if r.latency_ms is None else round(r.latency_ms,2)}\t"
                    f"{round(r.thr_bps,1)}\t{round(r.mega_thr_bps,1)}\t{r.mega_ok_streams}\t{r.mega_errors}\t"
                    f"{round(r.score,3)}\n")

    # Summary
    processed_per_sec = total / max(1e-6, duration_s)
    ok_count = len(good)
    latencies = [r.latency_ms for r in good if r.latency_ms is not None]
    thr_vals  = [r.thr_bps for r in good if r.thr_bps > 0]
    mega_vals = [r.mega_thr_bps for r in good if r.mega_thr_bps > 0]
    print("\n=== Benchmark Summary ===")
    print(f"Time taken: {duration_s:.2f} s")
    print(f"Total proxies tested: {total}")
    print(f"Processed/sec: {processed_per_sec:.2f}")
    print(f"Responsive (scored): {ok_count} ({(ok_count/total*100):.2f}% )")
    if good:
        print(f"Top score: {good[0].score:.2f}  ({fmt_hostport(good[0].host, good[0].port)} / {good[0].proto})")
    if latencies:
        print(f"Median latency: {median(latencies):.1f} ms")
    if thr_vals:
        print(f"Median Stage-B throughput: {median(thr_vals):.0f} B/s")
    if MEGA_MODE and mega_vals:
        print(f"Median MEGA throughput: {median(mega_vals):.0f} B/s "
              f"(streams={MEGA_STREAMS}, bytes/stream={MEGA_BYTES_PER_STREAM})")
    print(f"Selected for MBProxies.txt: {min(MIN_COUNT, len(selected))}/{MIN_COUNT} (threshold {SCORE_THRESHOLD})")
    print(f"Outputs: {all_path}, {mb_path}, "
          f"{Path(OUTPUT_DIR) / (CSV_NAME + ('.gz' if CSV_GZIP else '')) if os.environ.get('STREAM_CSV','0')=='1' else Path(OUTPUT_DIR) / (CSV_NAME + ('.gz' if CSV_GZIP else ''))}, "
          f"{tsv_path}")

# ------------------------
# Main
# ------------------------

def main():
    merged = load_and_dedupe()
    if not merged:
        print("No proxies found in inputs.", file=sys.stderr)
        sys.exit(1)

    if CROSS_PROTO_DEDUP:
        items = [(h, p, merged[(h, p)][0], merged[(h, p)][1], merged[(h, p)][2]) for (h, p) in merged.keys()]
    else:
        items = [(h, p, proto, merged[(h, p, proto)][0], merged[(h, p, proto)][1]) for (h, p, proto) in merged.keys()]

    if SHUFFLE_INPUT:
        try:
            random.shuffle(items)
        except Exception:
            pass

    start = time.perf_counter()
    results = asyncio.run(run_benchmark(items))
    duration_s = time.perf_counter() - start
    write_outputs(results, duration_s, total=len(items))

if __name__ == "__main__":
    main()
