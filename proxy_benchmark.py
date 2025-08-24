#!/usr/bin/env python3
# Proxy benchmark optimized for CI and large-download workloads.
# - IPv4-only parsing (no auth, no hostnames, no IPv6)
# - Stage 0: TCP prefilter (very fast)
# - Stage 1: burst + sustained throughput with stall detection
# - CI tuning via env: CI_TUNED=1, NO_TQDM=1, WORKERS=<int>, BENCH_URL=<url>
# - Exports:
#     Output/proxy_benchmark_results.csv
#     Output/proxy_history.csv
#     Output/MBProxies.txt                   (threshold + min count)
#     Output/megabasterd_http.txt            (host:port)
#     Output/megabasterd_socks5.txt          (host:port)

import os, sys, csv, re, ipaddress, random, asyncio
from time import perf_counter, time
from collections import defaultdict, deque
from typing import Optional, Tuple, List

import aiohttp
from aiohttp import ClientTimeout
from tqdm.asyncio import tqdm

try:
    from aiohttp_socks import ProxyConnector  # pip install aiohttp-socks
except ImportError as e:
    raise SystemExit("Missing dependency: aiohttp-socks. pip install aiohttp-socks") from e

# ===================== CI & RUNTIME KNOBS =====================
CI_TUNED   = os.getenv("CI_TUNED") == "1"
NO_TQDM    = bool(os.getenv("NO_TQDM"))
WORKERS    = None
for src in (len(sys.argv) > 1 and sys.argv[1], os.getenv("WORKERS")):
    try:
        if src:
            WORKERS = int(src)
            break
    except Exception:
        pass

# ===================== FILES & OUTPUT =====================
INPUT_HTTP   = "http.txt"
INPUT_SOCKS5 = "socks5.txt"
INPUT_SOCKS4 = "socks4.txt"

OUTPUT_DIR    = "Output"
CSV_FILE      = os.path.join(OUTPUT_DIR, "proxy_benchmark_results.csv")
HISTORY_FILE  = os.path.join(OUTPUT_DIR, "proxy_history.csv")
MBPROXIES_TXT = os.path.join(OUTPUT_DIR, "MBProxies.txt")
MB_HTTP_TXT   = os.path.join(OUTPUT_DIR, "megabasterd_http.txt")
MB_SOCKS5_TXT = os.path.join(OUTPUT_DIR, "megabasterd_socks5.txt")

# ===================== MB LIST CONTROLS =====================
MIN_MB_SCORE_THRESHOLD = 0.25
MIN_MB_COUNT           = 75

# ===================== SPEED/QUALITY DEFAULTS =====================
# Stage 0
TCP_TIMEOUT_S     = 0.8
TCP_CONCURRENCY   = 1500

# Targets: no MEGA URLs required. Fallback to public HTTPS files or BENCH_URL.
TEST_URLS = [u for u in [
    os.getenv("BENCH_URL"),
    "https://speed.hetzner.de/100MB.bin",
    "https://proof.ovh.net/files/100Mb.dat",
    "https://download.thinkbroadband.com/100MB.zip",
] if u]

# Stage 1
RANGE_BURST       = "bytes=0-2097151"   # ~2 MB
SUSTAIN_SECONDS   = 45                  # CI-safe sustained window
DL_CONNECT_TO     = 4
DL_SOCK_CONNECT   = 4
DL_SOCK_READ      = 8
HTTP_CONCURRENCY  = 384
SOCKS_CONCURRENCY = 256

# Early stop limits (None = test all)
EARLY_STOP_GOOD = {"http": None, "socks5": None, "socks4": None}
BATCH_SIZE      = 4000
HISTORY_MAX_RUNS = 12

# Apply global workers cap if provided
if WORKERS and WORKERS > 0:
    TCP_CONCURRENCY   = min(TCP_CONCURRENCY, WORKERS)
    HTTP_CONCURRENCY  = min(HTTP_CONCURRENCY, WORKERS)
    SOCKS_CONCURRENCY = min(SOCKS_CONCURRENCY, WORKERS)

# CI-safe overrides
_TOTAL_DL_TIMEOUT = None
if CI_TUNED:
    TCP_CONCURRENCY   = min(TCP_CONCURRENCY, 600)
    HTTP_CONCURRENCY  = min(HTTP_CONCURRENCY, 128)
    SOCKS_CONCURRENCY = min(SOCKS_CONCURRENCY, 128)
    BATCH_SIZE        = min(BATCH_SIZE, 500)
    _TOTAL_DL_TIMEOUT = 12
    DL_CONNECT_TO     = min(max(DL_CONNECT_TO, 4), 6)

# ===================== PARSING & UTILS =====================
_SCHEME_RE = re.compile(r'^(?P<scheme>https?|socks4|socks5)://', re.I)
_IPPORT_RE = re.compile(r'^(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d{1,5})$')

def _valid_port_str(port: str) -> bool:
    try:
        n = int(port); return 1 <= n <= 65535
    except: return False

def normalize_proxy_line(line: str, default_scheme: str) -> Optional[Tuple[str, str]]:
    s = (line or "").strip()
    if not s: return None
    m = _SCHEME_RE.match(s)
    scheme = default_scheme.lower()
    if m:
        scheme = m.group("scheme").lower()
        s = s[m.end():]
    if "@" in s:  # no auth
        return None
    m2 = _IPPORT_RE.match(s)
    if not m2:
        return None
    ip, port = m2.group("ip"), m2.group("port")
    try:
        ipaddr = ipaddress.IPv4Address(ip)
        if not ipaddr.is_global: return None
    except Exception:
        return None
    if not _valid_port_str(port): return None
    return scheme, f"{ip}:{port}"

def extract_host_port(authority: str) -> Optional[Tuple[str,int]]:
    try:
        ip, ps = authority.rsplit(":", 1); return ip, int(ps)
    except Exception:
        return None

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        print(f"Warning: {path} not found.")
        return []

def load_and_validate_lists():
    http_raw   = load_lines(INPUT_HTTP)
    socks5_raw = load_lines(INPUT_SOCKS5)
    socks4_raw = load_lines(INPUT_SOCKS4)

    def _filter(raw, expected):
        good, dropped = [], 0
        for line in raw:
            parsed = normalize_proxy_line(line, expected)
            if parsed is None: dropped += 1; continue
            scheme, authority = parsed
            if scheme == expected: good.append(authority)
            else: dropped += 1
        uniq = list(sorted(set(good)))
        dropped += len(good) - len(uniq)
        random.shuffle(uniq)
        return uniq, dropped

    http_list,   d_http = _filter(http_raw,   "http")
    socks5_list, d_s5   = _filter(socks5_raw, "socks5")
    socks4_list, d_s4   = _filter(socks4_raw, "socks4")
    print(f"Validation drops — HTTP: {d_http} | SOCKS5: {d_s5} | SOCKS4: {d_s4}")
    return http_list, socks5_list, socks4_list

# ===================== TIMING =====================
_timings: dict[str, float] = {}
async def timed(label: str, awaitable):
    t0 = perf_counter(); result = await awaitable; _timings[label] = perf_counter() - t0; return result

# ===================== JITTER =====================
async def sleep_jitter():
    await asyncio.sleep(random.uniform(0.02, 0.12) if CI_TUNED else random.uniform(0.0, 0.03))

# ===================== STAGE 0: TCP PREFILTER =====================
async def tcp_open(host: str, port: int, timeout_s: float) -> bool:
    try:
        fut = asyncio.open_connection(host=host, port=port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout_s)
        writer.close()
        try: await writer.wait_closed()
        except Exception: pass
        return True
    except Exception:
        return False

async def tcp_prefilter(authorities: List[str], concurrency: int, timeout_s: float,
                        early_stop_target: Optional[int] = None, label: str = "") -> List[str]:
    sem = asyncio.Semaphore(concurrency); alive = []
    async def one(auth: str):
        hp = extract_host_port(auth)
        if not hp: return None
        host, port = hp
        async with sem:
            return auth if await tcp_open(host, port, timeout_s) else None

    for i in range(0, len(authorities), BATCH_SIZE):
        batch = authorities[i:i+BATCH_SIZE]
        tasks = [one(a) for a in batch]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks),
                        desc=f"TCP prefilter {label} ({i//BATCH_SIZE+1})",
                        unit="proxy", disable=NO_TQDM):
            try:
                res = await asyncio.wait_for(fut, timeout=timeout_s + 0.4)
            except asyncio.TimeoutError:
                res = None
            if res:
                alive.append(res)
                if early_stop_target and len(alive) >= early_stop_target * 3:
                    return alive
    return alive

# ===================== STAGE 1: THROUGHPUT =====================
def make_http_session(limit: int) -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(ssl=False, limit=limit, ttl_dns_cache=300, enable_cleanup_closed=True)
    timeout = ClientTimeout(total=_TOTAL_DL_TIMEOUT, connect=DL_CONNECT_TO,
                            sock_connect=DL_SOCK_CONNECT, sock_read=DL_SOCK_READ)
    return aiohttp.ClientSession(connector=connector, timeout=timeout)

def make_socks_session(proxy_url: str) -> Optional[aiohttp.ClientSession]:
    try:
        # For remote DNS with hostnames use socks5h. We use IPv4 only, so standard socks5 is fine.
        connector = ProxyConnector.from_url(proxy_url, ttl_dns_cache=300)
    except Exception:
        return None
    timeout = ClientTimeout(total=_TOTAL_DL_TIMEOUT, connect=DL_CONNECT_TO,
                            sock_connect=DL_SOCK_CONNECT, sock_read=DL_SOCK_READ)
    return aiohttp.ClientSession(connector=connector, timeout=timeout)

async def timed_read(resp: aiohttp.ClientResponse, seconds: int) -> tuple[float,int,int]:
    total = 0; stalls = 0; chunks = 0
    t0 = perf_counter(); last = t0
    async for chunk in resp.content.iter_chunked(65536):
        total += len(chunk); chunks += 1
        now = perf_counter()
        if now - last > 1.5: stalls += 1
        last = now
        if seconds and now - t0 >= seconds: break
    dur = max(perf_counter() - t0, 1e-6)
    mbps = (total / dur) / 1024 / 1024
    return mbps, stalls, chunks

def pick_url() -> str:
    return random.choice(TEST_URLS)

async def download_http(session_http: aiohttp.ClientSession, authority: str):
    await sleep_jitter()
    url = pick_url()
    start = perf_counter()
    try:
        # Burst
        async with session_http.get(url, headers={"Range": RANGE_BURST}, proxy=f"http://{authority}") as r:
            if r.status not in (200, 206): raise RuntimeError(f"HTTP {r.status}")
            burst_mbps, _, _ = await timed_read(r, 0)
        # Sustained
        async with session_http.get(url, proxy=f"http://{authority}") as r2:
            if r2.status != 200: raise RuntimeError(f"HTTP {r2.status}")
            sus_mbps, stalls, _ = await timed_read(r2, SUSTAIN_SECONDS)
        elapsed = perf_counter() - start
        p95_proxy = max(sus_mbps, burst_mbps)
        score = 0.6*sus_mbps + 0.25*p95_proxy + 0.15*(1 - min(stalls,3)/3)
        return authority, "http", elapsed, sus_mbps, burst_mbps, stalls, score, True
    except Exception:
        return authority, "http", None, None, None, None, 0.0, False

async def download_socks(authority: str, scheme: str):
    await sleep_jitter()
    url = pick_url()
    session = make_socks_session(f"{scheme}://{authority}")
    if session is None:
        return authority, scheme, None, None, None, None, 0.0, False
    start = perf_counter()
    try:
        # Burst
        async with session.get(url, headers={"Range": RANGE_BURST}) as r:
            if r.status not in (200, 206): raise RuntimeError(f"HTTP {r.status}")
            burst_mbps, _, _ = await timed_read(r, 0)
        # Sustained
        async with session.get(url) as r2:
            if r2.status != 200: raise RuntimeError(f"HTTP {r2.status}")
            sus_mbps, stalls, _ = await timed_read(r2, SUSTAIN_SECONDS)
        elapsed = perf_counter() - start
        p95_proxy = max(sus_mbps, burst_mbps)
        score = 0.6*sus_mbps + 0.25*p95_proxy + 0.15*(1 - min(stalls,3)/3)
        return authority, scheme, elapsed, sus_mbps, burst_mbps, stalls, score, True
    except Exception:
        return authority, scheme, None, None, None, None, 0.0, False
    finally:
        try: await session.close()
        except Exception: pass

async def run_throughput_http(alive_http: List[str]) -> List[tuple]:
    results = []; sem = asyncio.Semaphore(HTTP_CONCURRENCY)
    async with make_http_session(HTTP_CONCURRENCY) as session_http:
        async def one(a):
            async with sem:
                return await download_http(session_http, a)
        stop_at = EARLY_STOP_GOOD["http"]
        for i in range(0, len(alive_http), BATCH_SIZE):
            batch = alive_http[i:i+BATCH_SIZE]
            tasks = [one(a) for a in batch]
            for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks),
                            desc=f"HTTP throughput ({i//BATCH_SIZE+1})",
                            unit="proxy", disable=NO_TQDM):
                res = await fut; results.append(res)
                if stop_at and sum(1 for r in results if r[7]) >= stop_at:
                    return results
    return results

async def run_throughput_socks(alive_socks: List[str], scheme: str, key: str) -> List[tuple]:
    results = []; sem = asyncio.Semaphore(SOCKS_CONCURRENCY)
    async def one(a):
        async with sem:
            return await download_socks(a, scheme)
    stop_at = EARLY_STOP_GOOD[key]
    for i in range(0, len(alive_socks), BATCH_SIZE):
        batch = alive_socks[i:i+BATCH_SIZE]
        tasks = [one(a) for a in batch]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks),
                        desc=f"{scheme.upper()} throughput ({i//BATCH_SIZE+1})",
                        unit="proxy", disable=NO_TQDM):
            res = await fut; results.append(res)
            if stop_at and sum(1 for r in results if r[7]) >= stop_at:
                return results
    return results

# ===================== HISTORY =====================
def load_history() -> defaultdict[str, deque]:
    hist = defaultdict(lambda: deque(maxlen=HISTORY_MAX_RUNS))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("ProxyKey") or row.get("Proxy")
                try: score = float(row.get("Score", "0") or 0)
                except: score = 0.0
                success = row.get("Success", "0") == "1"
                if key: hist[key].append((score, success))
    return hist

def save_history(hist: defaultdict[str, deque]):
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["ProxyKey","Timestamp","Score","Success"])
        now = int(time())
        for key, entries in hist.items():
            for score, success in entries:
                w.writerow([key, now, f"{score:.2f}", "1" if success else "0"])

# ===================== MBProxies writer =====================
def save_mbproxies(all_results: List[tuple], dest: str,
                   min_score: float, min_count: int) -> int:
    # result tuple: (proxy, scheme, elapsed, sus_mbps, burst_mbps, stalls, score, ok)
    successes = [r for r in all_results if r[7]]
    successes.sort(key=lambda r: r[6], reverse=True)  # by score
    selected, seen = [], set()
    # pass 1: threshold
    for r in successes:
        proxy = r[0]; sc = r[6]
        if sc < min_score or proxy in seen: continue
        seen.add(proxy); selected.append(proxy)
    # pass 2: top-up
    if len(selected) < min_count:
        for r in successes:
            proxy = r[0]
            if proxy in seen: continue
            seen.add(proxy); selected.append(proxy)
            if len(selected) >= min_count: break
    with open(dest, "w", encoding="utf-8") as f:
        for proxy in selected: f.write(proxy + "\n")
    return len(selected)

def write_megabasterd_lists(all_results: List[tuple]):
    ok_http   = [r[0] for r in all_results if r[7] and r[1]=="http"]
    ok_socks5 = [r[0] for r in all_results if r[7] and r[1]=="socks5"]
    with open(MB_HTTP_TXT, "w", encoding="utf-8") as f:
        for p in ok_http: f.write(p + "\n")
    with open(MB_SOCKS5_TXT, "w", encoding="utf-8") as f:
        for p in ok_socks5: f.write(p + "\n")

# ===================== MAIN =====================
async def main():
    ensure_output_dir()

    # Windows noise suppressor
    if sys.platform.startswith("win"):
        loop = asyncio.get_running_loop()
        def _win_handler(loop, context):
            exc = context.get("exception"); msg = context.get("message","")
            if isinstance(exc, ConnectionResetError) and "_ProactorBasePipeTransport._call_connection_lost" in msg:
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(_win_handler)

    if not TEST_URLS:
        raise SystemExit("No test URLs set. Define BENCH_URL or keep defaults.")

    print("Starting proxy benchmark (prefilter + burst + sustained)…")
    t0_all = perf_counter()

    http_list, socks5_list, socks4_list = load_and_validate_lists()
    print(f"Loaded (validated) — HTTP: {len(http_list)} | SOCKS5: {len(socks5_list)} | SOCKS4: {len(socks4_list)} | Total: {len(http_list)+len(socks5_list)+len(socks4_list)}")

    # Stage 0
    http_alive = await timed("TCP prefilter HTTP",
        tcp_prefilter(http_list,  TCP_CONCURRENCY, TCP_TIMEOUT_S, EARLY_STOP_GOOD["http"],   "HTTP")
    )
    s5_alive   = await timed("TCP prefilter SOCKS5",
        tcp_prefilter(socks5_list, TCP_CONCURRENCY, TCP_TIMEOUT_S, EARLY_STOP_GOOD["socks5"], "SOCKS5")
    )
    s4_alive   = await timed("TCP prefilter SOCKS4",
        tcp_prefilter(socks4_list, TCP_CONCURRENCY, TCP_TIMEOUT_S, EARLY_STOP_GOOD["socks4"], "SOCKS4")
    )
    print(f"TCP-alive — HTTP: {len(http_alive)} | SOCKS5: {len(s5_alive)} | SOCKS4: {len(s4_alive)}")

    # Stage 1
    http_res = await timed("HTTP throughput",  run_throughput_http(http_alive))
    s5_res   = await timed("SOCKS5 throughput", run_throughput_socks(s5_alive, "socks5", "socks5"))
    s4_res   = await timed("SOCKS4 throughput", run_throughput_socks(s4_alive, "socks4", "socks4"))

    all_results = http_res + s5_res + s4_res

    # History aggregation
    hist = load_history(); rows = []
    for proxy, scheme, elapsed, sus, burst, stalls, score, ok in all_results:
        key = f"{scheme}://{proxy}"
        hist[key].append((score, bool(ok)))
        entries = list(hist[key])
        lt = sum(s for s,_ in entries)/len(entries) if entries else score
        rr = (sum(1 for _,succ in entries if succ)/len(entries)*100.0) if entries else (100.0 if ok else 0.0)
        succ_scores = [s for s, succ in entries if succ]; ra = (sum(succ_scores)/len(succ_scores)) if succ_scores else 0.0
        rows.append((proxy, scheme, elapsed, sus, burst, stalls, score, lt, rr, ra))
    save_history(hist)

    # CSV
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Proxy","Protocol","Elapsed (s)","Sustained (MB/s)","Burst (MB/s)","Stalls",
            "Current Score","Long-Term Score","Response Rate (%)","Response AVG"
        ])
        for r in sorted(rows, key=lambda r: r[7], reverse=True):
            proxy, scheme, elapsed, sus, burst, stalls, score, lt, rr, ra = r
            w.writerow([
                proxy, scheme,
                f"{elapsed:.2f}" if elapsed else "",
                f"{sus:.2f}" if sus is not None else "",
                f"{burst:.2f}" if burst is not None else "",
                f"{stalls}"    if stalls is not None else "",
                f"{score:.2f}", f"{lt:.2f}",
                f"{rr:.1f}", f"{ra:.2f}"
            ])

    # MBProxies threshold + minimum count
    count_mb = save_mbproxies(all_results, MBPROXIES_TXT,
                              min_score=MIN_MB_SCORE_THRESHOLD,
                              min_count=MIN_MB_COUNT)

    # MegaBasterd-ready lists
    write_megabasterd_lists(all_results)

    # Timing summary
    total = perf_counter() - t0_all
    print("\n=== TIMING SUMMARY ===")
    for k in ["TCP prefilter HTTP","TCP prefilter SOCKS5","TCP prefilter SOCKS4",
              "HTTP throughput","SOCKS5 throughput","SOCKS4 throughput"]:
        if k in _timings: print(f"{k:>22}: {_timings[k]:6.2f}s")
    print(f"{'Total':>22}: {total:6.2f}s")

    ok_http   = sum(1 for r in http_res if r[7])
    ok_socks5 = sum(1 for r in s5_res   if r[7])
    ok_socks4 = sum(1 for r in s4_res   if r[7])
    print(f"\nDone.")
    print(f"Results CSV       : {CSV_FILE}")
    print(f"History CSV       : {HISTORY_FILE}")
    print(f"MBProxies         : {MBPROXIES_TXT}  [{count_mb} proxies | min score {MIN_MB_SCORE_THRESHOLD} | min count {MIN_MB_COUNT}]")
    print(f"MegaBasterd lists : {MB_HTTP_TXT}, {MB_SOCKS5_TXT}")
    print(f"Successful — HTTP: {ok_http} | SOCKS5: {ok_socks5} | SOCKS4: {ok_socks4} | Total: {ok_http + ok_socks5 + ok_socks4}")

if __name__ == "__main__":
    asyncio.run(main())
