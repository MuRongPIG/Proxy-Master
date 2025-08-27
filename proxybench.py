#!/usr/bin/env python3
# proxybench.py
# Purpose: From large scraped free proxy lists, quickly weed out dead proxies,
# sample throughput, and rank for fast real-world downloads (e.g., MegaBasterd).

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import ipaddress

# Dependencies:#!/usr/bin/env python3
# proxybench.py — ranked proxy benchmarking with CSV output + live progress

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import ipaddress
import csv
from statistics import median

# Deps: pip install "httpx[socks]" anyio tqdm
import httpx
from tqdm import tqdm

# ------------------------
# Config (env-overridable)
# ------------------------
INPUT_DIR = os.environ.get("INPUT_DIR", ".")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "Output")

INPUT_FILES = {
    "socks5": os.path.join(INPUT_DIR, "socks5.txt"),
    "http":   os.path.join(INPUT_DIR, "http.txt"),
    "socks4": os.path.join(INPUT_DIR, "socks4.txt"),
}

TEST_URL = os.environ.get("TEST_URL", "https://cachefly.cachefly.net/10mb.test")

CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "2.5"))
READ_TIMEOUT_S    = float(os.environ.get("READ_TIMEOUT_S", "3.0"))
A_SAMPLE_BYTES    = int(os.environ.get("A_SAMPLE_BYTES", "32768"))

B_SAMPLE_BYTES    = int(os.environ.get("B_SAMPLE_BYTES", "512000"))
B_MAX_DURATION_S  = float(os.environ.get("B_MAX_DURATION_S", "3.5"))

WORKERS           = int(os.environ.get("WORKERS", "300"))
PER_HOST_LIMIT    = int(os.environ.get("PER_HOST_LIMIT", "32"))

THR_WEIGHT        = float(os.environ.get("THR_WEIGHT", "0.001"))
LAT_PENALTY       = float(os.environ.get("LAT_PENALTY", "0.25"))

MIN_COUNT         = int(os.environ.get("MIN_COUNT", "75"))
SCORE_THRESHOLD   = float(os.environ.get("SCORE_THRESHOLD", "50.0"))

SHUFFLE_INPUT     = os.environ.get("SHUFFLE_INPUT", "1") == "1"

CSV_NAME          = os.environ.get("CSV_NAME", "MBProxies.csv")
TSV_NAME          = os.environ.get("TSV_NAME", "MBProxies.meta.tsv")  # kept for continuity

PROTO_PRIORITY = {"socks5": 3, "http": 2, "socks4": 1}

# ------------------------
# Helpers
# ------------------------

def parse_line(line: str) -> Optional[Tuple[str, int]]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    host, port = None, None
    if s.startswith("["):
        try:
            right = s.index("]")
            host = s[1:right]
            if s[right+1:right+2] != ":":
                return None
            port = int(s[right+2:])
        except Exception:
            return None
    else:
        parts = s.split(":")
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
        ipaddress.ip_address(host)
    except Exception:
        if any(c.isspace() for c in host) or len(host) > 255:
            return None
    return host, port

def load_and_dedupe() -> Dict[Tuple[str, int], str]:
    merged: Dict[Tuple[str, int], str] = {}
    for proto, path in INPUT_FILES.items():
        p = Path(path)
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                hp = parse_line(line)
                if not hp:
                    continue
                if hp not in merged or PROTO_PRIORITY[proto] > PROTO_PRIORITY[merged[hp]]:
                    merged[hp] = proto
    return merged

def proxy_url(proto: str, host: str, port: int) -> str:
    if proto == "socks5":
        return f"socks5://{host}:{port}"
    if proto == "socks4":
        return f"socks4://{host}:{port}"
    return f"http://{host}:{port}"

def fmt_hostport(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"

# ------------------------
# Benchmarking
# ------------------------

class BenchResult:
    __slots__ = ("host","port","proto","ok","latency_ms","thr_bps","score")
    def __init__(self, host, port, proto):
        self.host = host
        self.port = port
        self.proto = proto
        self.ok = False
        self.latency_ms = None
        self.thr_bps = 0.0
        self.score = -1e9
    def calc_score(self):
        if self.latency_ms is None or self.thr_bps <= 0:
            self.score = -1e9
        else:
            self.score = (self.thr_bps * THR_WEIGHT) - (self.latency_ms * LAT_PENALTY)

async def stage_a_quick_check(client: httpx.AsyncClient, proxy: str) -> Tuple[bool, Optional[float]]:
    start = time.perf_counter()
    try:
        with httpx.Timeout(CONNECT_TIMEOUT_S + READ_TIMEOUT_S):
            async with client.stream(
                "GET", TEST_URL,
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=CONNECT_TIMEOUT_S),
                proxies=proxy
            ) as resp:
                if resp.status_code >= 400:
                    return False, None
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total >= A_SAMPLE_BYTES:
                        break
        latency_ms = (time.perf_counter() - start) * 1000.0
        return True, latency_ms
    except Exception:
        return False, None

async def stage_b_throughput(client: httpx.AsyncClient, proxy: str) -> float:
    start = time.perf_counter()
    got = 0
    try:
        async with client.stream(
            "GET", TEST_URL,
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=B_MAX_DURATION_S + 0.5, write=CONNECT_TIMEOUT_S),
            proxies=proxy
        ) as resp:
            if resp.status_code >= 400:
                return 0.0
            async for chunk in resp.aiter_bytes():
                got += len(chunk)
                if got >= B_SAMPLE_BYTES:
                    break
                if (time.perf_counter() - start) >= B_MAX_DURATION_S:
                    break
    except Exception:
        return 0.0
    dur = max(1e-6, time.perf_counter() - start)
    return got / dur

async def worker(queue: asyncio.Queue, results: List["BenchResult"], client: httpx.AsyncClient, pbar: tqdm):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        host, port, proto = item
        br = BenchResult(host, port, proto)
        purl = proxy_url(proto, host, port)

        ok, latency = await stage_a_quick_check(client, purl)
        if ok and latency is not None:
            br.latency_ms = latency
            thr = await stage_b_throughput(client, purl)
            br.thr_bps = thr
            if thr > 0:
                br.ok = True
                br.calc_score()

        results.append(br)
        pbar.update(1)  # live progress
        queue.task_done()

async def run_benchmark(proxies: List[Tuple[str,int,str]]) -> List["BenchResult"]:
    results: List[BenchResult] = []
    limits = httpx.Limits(max_connections=WORKERS, max_keepalive_connections=PER_HOST_LIMIT)
    async with httpx.AsyncClient(http2=False, limits=limits, verify=True) as client:
        q: asyncio.Queue = asyncio.Queue()
        for host, port, proto in proxies:
            q.put_nowait((host, port, proto))
        for _ in range(WORKERS):
            q.put_nowait(None)

        # tqdm progress bar
        with tqdm(total=len(proxies), desc="Benchmarking", unit="proxy", smoothing=0.1, miniters=1) as pbar:
            tasks = [asyncio.create_task(worker(q, results, client, pbar)) for _ in range(WORKERS)]
            await q.join()
            for t in tasks:
                await t
    return results

# ------------------------
# Outputs and summary
# ------------------------

def write_outputs(results: List["BenchResult"], duration_s: float, total: int):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # All responsive, sorted best->worst
    good = [r for r in results if r.ok]
    good.sort(key=lambda r: r.score, reverse=True)

    # Text lists
    all_path = Path(OUTPUT_DIR) / "MBProxiesAll.txt"
    with all_path.open("w", encoding="utf-8") as f:
        for r in good:
            f.write(f"{fmt_hostport(r.host, r.port)}\n")

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

    # CSV with columns per metric
    csv_path = Path(OUTPUT_DIR) / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["host","port","proto","ok","latency_ms","thr_bps","score"])
        for r in results:
            w.writerow([
                r.host, r.port, r.proto, int(r.ok),
                0 if r.latency_ms is None else round(r.latency_ms, 3),
                round(r.thr_bps, 1),
                round(r.score, 3),
            ])

    # Optional TSV for continuity/debug
    tsv_path = Path(OUTPUT_DIR) / TSV_NAME
    with tsv_path.open("w", encoding="utf-8") as f:
        f.write("host\tport\tproto\tok\tlatency_ms\tthr_bps\tscore\n")
        for r in results:
            f.write(f"{r.host}\t{r.port}\t{r.proto}\t{int(r.ok)}\t"
                    f"{0 if r.latency_ms is None else round(r.latency_ms,2)}\t"
                    f"{round(r.thr_bps,1)}\t{round(r.score,3)}\n")

    # Console summary (for CI logs)
    processed_per_sec = total / max(1e-6, duration_s)
    ok_count = len(good)
    latencies = [r.latency_ms for r in good if r.latency_ms is not None]
    thr_vals  = [r.thr_bps for r in good if r.thr_bps > 0]
    print("\n=== Benchmark Summary ===")
    print(f"Time taken: {duration_s:.2f} s")
    print(f"Total proxies tested: {total}")
    print(f"Processed/sec: {processed_per_sec:.2f}")
    print(f"Responsive: {ok_count} ({(ok_count/total*100):.2f}% )")
    if good:
        print(f"Top score: {good[0].score:.2f}  ({fmt_hostport(good[0].host, good[0].port)} / {good[0].proto})")
    if latencies:
        print(f"Median latency: {median(latencies):.1f} ms")
    if thr_vals:
        print(f"Median throughput: {median(thr_vals):.0f} B/s")
    print(f"Selected for MBProxies.txt: {min(MIN_COUNT, len(selected))}/{MIN_COUNT} "
          f"(threshold {SCORE_THRESHOLD})")
    print(f"Outputs: {all_path}, {mb_path}, {csv_path}, {tsv_path}")

# ------------------------
# Main
# ------------------------

def main():
    merged = load_and_dedupe()
    if not merged:
        print("No proxies found in inputs.", file=sys.stderr)
        sys.exit(1)

    items = [(h, p, merged[(h,p)]) for (h,p) in merged.keys()]
    if SHUFFLE_INPUT:
        try:
            import random
            random.shuffle(items)
        except Exception:
            pass

    start = time.perf_counter()
    results = asyncio.run(run_benchmark(items))
    duration_s = time.perf_counter() - start
    write_outputs(results, duration_s, total=len(items))

if __name__ == "__main__":
    main()

#   pip install "httpx[socks]" anyio
import httpx

# ------------------------
# Config (env-overridable)
# ------------------------
INPUT_DIR = os.environ.get("INPUT_DIR", ".")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "Output")

# Your getproxy.py outputs: socks4.txt, socks5.txt, http.txt (http + https mixed)
INPUT_FILES = {
    "socks5": os.path.join(INPUT_DIR, "socks5.txt"),
    "http":   os.path.join(INPUT_DIR, "http.txt"),
    "socks4": os.path.join(INPUT_DIR, "socks4.txt"),
}

# Fast, stable test asset (configurable). You can switch to your own CDN/object.
TEST_URL = os.environ.get("TEST_URL", "https://cachefly.cachefly.net/10mb.test")

# Stage A: quick weed-out
CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "2.5"))
READ_TIMEOUT_S    = float(os.environ.get("READ_TIMEOUT_S", "3.0"))
A_SAMPLE_BYTES    = int(os.environ.get("A_SAMPLE_BYTES", "32_768"))   # 32 KB sniff

# Stage B: capped throughput sample
B_SAMPLE_BYTES    = int(os.environ.get("B_SAMPLE_BYTES", "512_000"))  # ~0.5 MB
B_MAX_DURATION_S  = float(os.environ.get("B_MAX_DURATION_S", "3.5"))  # hard cap

# Concurrency knobs for CI
WORKERS           = int(os.environ.get("WORKERS", "300"))             # GH Actions friendly
PER_HOST_LIMIT    = int(os.environ.get("PER_HOST_LIMIT", "32"))

# Scoring weights
# Score = (throughput_bytes_per_sec * THR_WEIGHT) - (latency_ms * LAT_PENALTY)
THR_WEIGHT        = float(os.environ.get("THR_WEIGHT", "0.001"))      # scales B/s into score
LAT_PENALTY       = float(os.environ.get("LAT_PENALTY", "0.25"))      # ms penalty

# Selection threshold for MBProxies.txt
# "Relatively low": accept anything scoring above this; then backfill to 75.
MIN_COUNT         = int(os.environ.get("MIN_COUNT", "75"))
SCORE_THRESHOLD   = float(os.environ.get("SCORE_THRESHOLD", "50.0"))

# Randomize ordering before testing to avoid server-side correlation effects
SHUFFLE_INPUT     = os.environ.get("SHUFFLE_INPUT", "1") == "1"

# ------------------------
# Helpers
# ------------------------

PROTO_PRIORITY = {"socks5": 3, "http": 2, "socks4": 1}

def parse_line(line: str) -> Optional[Tuple[str, int]]:
    # Accept host:port where host may be IPv4/IPv6/domain
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    # Support IPv6 like [2001:db8::1]:1080
    host, port = None, None
    if s.startswith("["):
        # IPv6 in brackets
        try:
            right = s.index("]")
            host = s[1:right]
            if s[right+1:right+2] != ":":
                return None
            port = int(s[right+2:])
        except Exception:
            return None
    else:
        parts = s.split(":")
        if len(parts) != 2:
            return None
        host, port_s = parts
        try:
            port = int(port_s)
        except ValueError:
            return None
    if port < 1 or port > 65535:
        return None
    # quick sanity on host
    try:
        # allow IPv4/IPv6; if domain, this will raise which we ignore
        ipaddress.ip_address(host)
    except Exception:
        # domain or invalid; keep domain, drop obvious junk
        if any(c.isspace() for c in host) or len(host) > 255:
            return None
    return host, port

def load_and_dedupe() -> Dict[Tuple[str, int], str]:
    """
    Return mapping: (host,port) -> protocol chosen by priority
    Priority: socks5 > http/https > socks4
    """
    merged: Dict[Tuple[str, int], str] = {}
    for proto, path in INPUT_FILES.items():
        p = Path(path)
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                hp = parse_line(line)
                if not hp:
                    continue
                if hp not in merged:
                    merged[hp] = proto
                else:
                    # upgrade if higher priority
                    if PROTO_PRIORITY[proto] > PROTO_PRIORITY[merged[hp]]:
                        merged[hp] = proto
    return merged

def proxy_url(proto: str, host: str, port: int) -> str:
    # httpx proxy scheme names
    # http list includes both http and https entries; we’ll use "http://"
    if proto == "socks5":
        return f"socks5://{host}:{port}"
    elif proto == "socks4":
        return f"socks4://{host}:{port}"
    else:
        return f"http://{host}:{port}"

def fmt_hostport(host: str, port: int) -> str:
    # Output format host:port. If the user truly needs [host]:[ip], adjust here.
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"

# ------------------------
# Benchmarking
# ------------------------

class BenchResult:
    __slots__ = ("host","port","proto","ok","latency_ms","thr_bps","score")
    def __init__(self, host, port, proto):
        self.host = host
        self.port = port
        self.proto = proto
        self.ok = False
        self.latency_ms = None
        self.thr_bps = 0.0
        self.score = -1e9

    def calc_score(self):
        if self.latency_ms is None or self.thr_bps <= 0:
            self.score = -1e9
        else:
            self.score = (self.thr_bps * THR_WEIGHT) - (self.latency_ms * LAT_PENALTY)

async def stage_a_quick_check(client: httpx.AsyncClient, proxy: str) -> Tuple[bool, Optional[float]]:
    """
    Quick connect + small read. Returns (ok, latency_ms).
    """
    start = time.perf_counter()
    try:
        # Small range to avoid big transfer; not all servers honor Range. We stream and stop after A_SAMPLE_BYTES.
        with httpx.Timeout(CONNECT_TIMEOUT_S + READ_TIMEOUT_S):
            async with client.stream("GET", TEST_URL, timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=CONNECT_TIMEOUT_S
            ), proxies=proxy) as resp:
                if resp.status_code >= 400:
                    return False, None
                # Read a tiny chunk to confirm data flow
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total >= A_SAMPLE_BYTES:
                        break
        latency_ms = (time.perf_counter() - start) * 1000.0
        return True, latency_ms
    except Exception:
        return False, None

async def stage_b_throughput(client: httpx.AsyncClient, proxy: str) -> float:
    """
    Stream up to B_SAMPLE_BYTES or B_MAX_DURATION_S and return bytes/sec.
    """
    start = time.perf_counter()
    got = 0
    try:
        async with client.stream("GET", TEST_URL, timeout=httpx.Timeout(
            connect=CONNECT_TIMEOUT_S, read=B_MAX_DURATION_S + 0.5, write=CONNECT_TIMEOUT_S
        ), proxies=proxy) as resp:
            if resp.status_code >= 400:
                return 0.0
            async for chunk in resp.aiter_bytes():
                got += len(chunk)
                if got >= B_SAMPLE_BYTES:
                    break
                if (time.perf_counter() - start) >= B_MAX_DURATION_S:
                    break
    except Exception:
        return 0.0
    dur = max(1e-6, time.perf_counter() - start)
    return got / dur

async def worker(queue: asyncio.Queue, results: List[BenchResult], client: httpx.AsyncClient):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        host, port, proto = item
        br = BenchResult(host, port, proto)
        purl = proxy_url(proto, host, port)

        ok, latency = await stage_a_quick_check(client, purl)
        if ok and latency is not None:
            br.latency_ms = latency
            thr = await stage_b_throughput(client, purl)
            br.thr_bps = thr
            if thr > 0:
                br.ok = True
                br.calc_score()
        results.append(br)
        queue.task_done()

async def run_benchmark(proxies: List[Tuple[str,int,str]]) -> List[BenchResult]:
    results: List[BenchResult] = []
    limits = httpx.Limits(max_connections=WORKERS, max_keepalive_connections=PER_HOST_LIMIT)
    async with httpx.AsyncClient(http2=False, limits=limits, verify=True) as client:
        q: asyncio.Queue = asyncio.Queue()
        for host, port, proto in proxies:
            q.put_nowait((host, port, proto))
        for _ in range(WORKERS):
            q.put_nowait(None)
        tasks = [asyncio.create_task(worker(q, results, client)) for _ in range(WORKERS)]
        await q.join()
        for t in tasks:
            await t
    return results

# ------------------------
# Main
# ------------------------

def write_outputs(results: List[BenchResult]):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # All responsive, sorted best->worst
    good = [r for r in results if r.ok]
    good.sort(key=lambda r: r.score, reverse=True)

    all_path = Path(OUTPUT_DIR) / "MBProxiesAll.txt"
    with all_path.open("w", encoding="utf-8") as f:
        for r in good:
            f.write(f"{fmt_hostport(r.host, r.port)}\n")

    # Threshold then backfill to MIN_COUNT
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

    # Minimal debug file to aid CI runs
    meta_path = Path(OUTPUT_DIR) / "MBProxies.meta.tsv"
    with meta_path.open("w", encoding="utf-8") as f:
        f.write("host\tport\tproto\tok\tlatency_ms\tthr_bps\tscore\n")
        for r in good:
            f.write(f"{r.host}\t{r.port}\t{r.proto}\t{int(r.ok)}\t"
                    f"{0 if r.latency_ms is None else round(r.latency_ms,2)}\t"
                    f"{round(r.thr_bps,1)}\t{round(r.score,2)}\n")

def main():
    merged = load_and_dedupe()
    if not merged:
        print("No proxies found in inputs.", file=sys.stderr)
        sys.exit(1)

    items = [(h, p, merged[(h,p)]) for (h,p) in merged.keys()]
    if SHUFFLE_INPUT:
        try:
            import random
            random.shuffle(items)
        except Exception:
            pass

    # Run
    results = asyncio.run(run_benchmark(items))
    write_outputs(results)

if __name__ == "__main__":
    main()
