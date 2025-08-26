#!/usr/bin/env python3
"""
Proxy Benchmark Script
Tests proxy performance and reliability for MegaBasterd downloads.
"""

import sys
import os
import csv
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from time import perf_counter, time
from tqdm.asyncio import tqdm
from collections import defaultdict, deque

# SETTINGS - Updated to use getproxy.py output files
PROXY_FILE_HTTP     = "http.txt"
PROXY_FILE_SOCKS5   = "socks5.txt"
PROXY_FILE_SOCKS4   = "socks4.txt"
OUTPUT_DIR          = "Output"
CSV_FILE            = os.path.join(OUTPUT_DIR, "proxy_benchmark_results.csv")
HISTORY_FILE        = os.path.join(OUTPUT_DIR, "proxy_history.csv")
MB_PROXIES_FILE     = os.path.join(OUTPUT_DIR, "MBProxies.txt")
MB_PROXIES_ALL_FILE = os.path.join(OUTPUT_DIR, "MBProxiesAll.txt")

# TEST SETTINGS - Optimized for sustained download performance
TEST_URL            = "http://speedtest.tele2.net/10MB.zip"  # Smaller test file
TEST_URLS_BACKUP    = [  # Fallback URLs if primary fails
    "http://ipv4.download.thinkbroadband.com/5MB.zip",
    "http://speedtest.ftp.otenet.gr/files/test5Mb.db"
]
CHUNK_SIZE          = 524288   # 512KB chunks for more frequent updates
CHUNK_RANGE         = "bytes=0-5242880"  # First 5 MB for quicker tests
TIMEOUT             = 30                  # Longer timeout for slower proxies
CONNECT_TIMEOUT     = 10                  # More time for SOCKS connection setup
CONCURRENT_LIMIT    = 512                 # Max simultaneous tasks
MAX_RETRIES         = 2                   # Retry count for borderline proxies
HISTORY_MAX_RUNS    = 10                  # Keep last N runs per proxy
MIN_TESTS_FOR_FAIL  = 3                   # Threshold to consider continuous failures

# PERFORMANCE CUTOFF SETTINGS
MIN_SCORE_THRESHOLD = 0.25                # More lenient score threshold
MIN_SPEED_THRESHOLD = 0.5                 # Lower minimum speed requirement (500KB/s)
MIN_RESPONSE_RATE   = 50.0                # Lower response rate requirement
MIN_PROXIES_COUNT   = 50                  # Reduced minimum proxy count

# PRE-SCREENING SETTINGS
PRE_SCREEN_URL      = "http://ip-api.com/json/"  # Alternative IP check service
PRE_SCREEN_TIMEOUT  = 10                  # Increased pre-screening timeout
PRE_SCREEN_CONCURRENT = 256               # Reduced concurrent connections

# GLOBAL RESULTS
good, bad = [], []
sem = asyncio.Semaphore(CONCURRENT_LIMIT)
pre_screen_sem = asyncio.Semaphore(PRE_SCREEN_CONCURRENT)

def ensure_output_directory():
    """Create the Output directory if it doesn't exist."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created output directory: {OUTPUT_DIR}")

async def pre_screen_proxy(session, proxy: str, scheme: str) -> tuple:
    """Quick connectivity test to filter out dead proxies before performance testing."""
    proxy_url = f"{scheme}://{proxy}"
    try:
        async with pre_screen_sem:
            timeout = aiohttp.ClientTimeout(total=PRE_SCREEN_TIMEOUT)
            async with session.get(PRE_SCREEN_URL, proxy=proxy_url, timeout=timeout) as resp:
                if resp.status == 200:
                    return proxy, scheme, True
                else:
                    return proxy, scheme, False
    except Exception:
        return proxy, scheme, False

async def pre_screen_proxies(proxies: list, scheme: str) -> list:
    """Pre-screen proxies to filter out dead ones before performance testing."""
    print(f"Pre-screening {len(proxies)} {scheme.upper()} proxies...")
    if scheme.startswith("socks"):
        connector = ProxyConnector.from_url(f"{scheme}://127.0.0.1:0")  # Dummy, actual proxy set per request
    else:
        connector = aiohttp.TCPConnector(ssl=False, limit=None)
    timeout = aiohttp.ClientTimeout(total=PRE_SCREEN_TIMEOUT)
    
    responsive_proxies = []
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [pre_screen_proxy(session, p, scheme) for p in proxies]
        
        for future in tqdm(asyncio.as_completed(tasks),
                           total=len(tasks),
                           desc=f"Pre-screening {scheme.upper()}",
                           unit="proxy"):
            proxy, proxy_scheme, is_responsive = await future
            if is_responsive:
                responsive_proxies.append(proxy)
    
    print(f"Pre-screening complete: {len(responsive_proxies)}/{len(proxies)} {scheme.upper()} proxies are responsive")
    if not responsive_proxies:
        print(f"Warning: No responsive {scheme.upper()} proxies found in pre-screening.")
    return responsive_proxies

async def try_proxy(session, proxy: str, scheme: str) -> tuple:
    proxy_url = f"{scheme}://{proxy}"
    headers   = {"Range": CHUNK_RANGE}
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with sem:
                start = perf_counter()
                async with session.get(TEST_URL, headers=headers, proxy=proxy_url,
                                    timeout=aiohttp.ClientTimeout(total=TIMEOUT,
                                                               connect=CONNECT_TIMEOUT)) as resp:
                    if resp.status not in (200, 206):
                        raise Exception(f"HTTP {resp.status}")
                    
                    total = 0
                    chunk_times = []
                    last_chunk_time = perf_counter()
                    
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        now = perf_counter()
                        chunk_times.append(now - last_chunk_time)
                        last_chunk_time = now
                        total += len(chunk)
                        if total >= 10 * 1024 * 1024:
                            break
                    
                    elapsed = perf_counter() - start
                    speed = total / elapsed / 1024 / 1024
                    latency = elapsed
                    
                    # Calculate stability score based on chunk timing consistency
                    avg_chunk_time = sum(chunk_times) / len(chunk_times)
                    stability = sum(1 for t in chunk_times if abs(t - avg_chunk_time) < 0.5) / len(chunk_times)
                    
                    # Calculate final score incorporating speed, latency, and stability
                    score = (speed * stability) / (latency + 0.01)
                    
                    # More lenient speed check
                    if speed >= MIN_SPEED_THRESHOLD or (score >= MIN_SCORE_THRESHOLD and stability >= 0.5):
                        good.append(proxy)
                        return proxy, scheme, latency, speed, score, True
                    else:
                        raise Exception(f"Performance below threshold: speed={speed:.2f}MB/s score={score:.2f}")

        except Exception as e:
            if attempt == MAX_RETRIES:
                bad.append(proxy)
                return proxy, scheme, None, None, 0.0, False
            await asyncio.sleep(0.5)  # Brief pause before retry
            continue

async def run_tests(proxies: list, scheme: str):
    if scheme.startswith("socks"):
        connector = ProxyConnector.from_url(f"{scheme}://127.0.0.1:0")  # Dummy, actual proxy set per request
    else:
        connector = aiohttp.TCPConnector(ssl=False, limit=None)
    timeout   = aiohttp.ClientTimeout(total=TIMEOUT)
    results   = []
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [try_proxy(session, p, scheme) for p in proxies]
        for future in tqdm(asyncio.as_completed(tasks),
                           total=len(tasks),
                           desc=f"Testing {scheme.upper()}",
                           unit="proxy"):
            res = await future
            results.append(res)
    return results

def load_proxies(path: str):
    try:
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Warning: {path} not found. Skipping {path.split('.')[0]} proxies.")
        return []

def deduplicate_within_protocol(proxy_list: list) -> list:
    """Remove duplicates within a single protocol list."""
    return list(dict.fromkeys(proxy_list))

def remove_duplicates(http_list: list, socks5_list: list, socks4_list: list) -> tuple:
    """Remove duplicate IP:port combinations, prioritizing SOCKS5 > HTTP > SOCKS4."""
    print("Checking for duplicate IP:port combinations...")
    http_ips = set(http_list)
    socks5_ips = set(socks5_list)
    socks4_ips = set(socks4_list)
    all_ips = http_ips | socks5_ips | socks4_ips
    final_http, final_socks5, final_socks4 = [], [], []
    for ip in all_ips:
        if ip in socks5_ips:
            final_socks5.append(ip)
        elif ip in http_ips:
            final_http.append(ip)
        elif ip in socks4_ips:
            final_socks4.append(ip)
    return final_http, final_socks5, final_socks4

def load_history():
    history = defaultdict(lambda: deque(maxlen=HISTORY_MAX_RUNS))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row or 'Proxy' not in row or 'Score' not in row or 'Success' not in row:
                    continue  # skip malformed or headerless rows
                try:
                    proxy = row['Proxy']
                    score = float(row['Score'])
                    success = row['Success'] == '1'
                    history[proxy].append((score, success))
                except Exception:
                    continue  # skip rows with conversion errors
    return history

def save_history(history):
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Proxy", "Timestamp", "Score", "Success"])
        for proxy, entries in history.items():
            for score, success in entries:
                writer.writerow([proxy, int(time()), f"{score:.2f}", '1' if success else '0'])

def save_mb_proxies(sorted_rows):
    qualified_proxies = []
    for proxy, scheme, lat, spd, sc, lt, rr, ra, status in sorted_rows:
        if (sc >= MIN_SCORE_THRESHOLD and rr >= MIN_RESPONSE_RATE and lat is not None and spd is not None):
            qualified_proxies.append((proxy, sc))
    if not qualified_proxies:
        print("Warning: No proxies met the quality criteria!")
        return 0
    qualified_proxies.sort(key=lambda x: x[1], reverse=True)
    total_qualified = len(qualified_proxies)
    if total_qualified >= MIN_PROXIES_COUNT:
        final_proxies = qualified_proxies
        print(f"Found {total_qualified} qualified proxies (above minimum {MIN_PROXIES_COUNT})")
        print(f"Including all {total_qualified} qualified proxies")
    else:
        print(f"Only {total_qualified} proxies met quality criteria (below minimum {MIN_PROXIES_COUNT})")
        print(f"Adding fallback proxies to reach minimum {MIN_PROXIES_COUNT}")
        final_proxies = qualified_proxies.copy()
        fallback_proxies = []
        for proxy, scheme, lat, spd, sc, lt, rr, ra, status in sorted_rows:
            if proxy not in [p[0] for p in final_proxies] and lat is not None and spd is not None:
                fallback_proxies.append((proxy, sc))
        fallback_proxies.sort(key=lambda x: x[1], reverse=True)
        needed_fallback = MIN_PROXIES_COUNT - total_qualified
        fallback_to_add = fallback_proxies[:needed_fallback]
        final_proxies.extend(fallback_to_add)
        print(f"Added {len(fallback_to_add)} fallback proxies (total: {len(final_proxies)})")
    with open(MB_PROXIES_FILE, "w") as f:
        for proxy, _ in final_proxies:
            f.write(f"{proxy}\n")
    print(f"Saved {len(final_proxies)} proxies to {MB_PROXIES_FILE}")
    return len(final_proxies)

def save_all_proxies(sorted_rows):
    working_proxies = []
    for proxy, scheme, lat, spd, sc, lt, rr, ra, status in sorted_rows:
        if lat is not None and spd is not None:
            working_proxies.append((proxy, sc))
    working_proxies.sort(key=lambda x: x[1], reverse=True)
    with open(MB_PROXIES_ALL_FILE, "w") as f:
        for proxy, _ in working_proxies:
            f.write(f"{proxy}\n")
    print(f"Saved {len(working_proxies)} working proxies to {MB_PROXIES_ALL_FILE}")
    return len(working_proxies)

async def main():
    print("Starting proxy benchmark...")
    print(f"Loading proxies from: {PROXY_FILE_HTTP}, {PROXY_FILE_SOCKS5}, {PROXY_FILE_SOCKS4}")
    ensure_output_directory()
    t0 = perf_counter()
    http_list = load_proxies(PROXY_FILE_HTTP)
    socks5_list = load_proxies(PROXY_FILE_SOCKS5)
    socks4_list = load_proxies(PROXY_FILE_SOCKS4)
    http_list, socks5_list, socks4_list = remove_duplicates(http_list, socks5_list, socks4_list)
    total_proxies = len(http_list) + len(socks5_list) + len(socks4_list)
    if total_proxies == 0:
        print("No proxies found! Make sure proxy files exist and are not empty.")
        return
    print(f"Loaded {len(http_list)} HTTP, {len(socks5_list)} SOCKS5, {len(socks4_list)} SOCKS4 proxies")
    print(f"Total proxies loaded: {total_proxies}")
    total_proxies_after_dedup = len(http_list) + len(socks5_list) + len(socks4_list)
    print(f"After deduplication: {len(http_list)} HTTP, {len(socks5_list)} SOCKS5, {len(socks4_list)} SOCKS4 proxies")
    print(f"Total proxies after deduplication: {total_proxies_after_dedup}")

    print("\n=== PRE-SCREENING PHASE ===")
    http_proxies_to_test = await pre_screen_proxies(http_list, "http")
    socks5_proxies_to_test = await pre_screen_proxies(socks5_list, "socks5")
    socks4_proxies_to_test = await pre_screen_proxies(socks4_list, "socks4")

    all_proxies_to_test = http_proxies_to_test + socks5_proxies_to_test + socks4_proxies_to_test
    if not all_proxies_to_test:
        print("No responsive proxies found after pre-screening!")
        return

    print(f"\n=== PERFORMANCE TESTING PHASE ===")
    print(f"Proxies to test: {len(all_proxies_to_test)} (filtered from {total_proxies_after_dedup} total)")
    print(f"Filtered out: {total_proxies_after_dedup - len(all_proxies_to_test)} dead/unresponsive proxies")

    all_results = []
    if http_proxies_to_test:
        all_results.extend(await run_tests(http_proxies_to_test, "http"))
    if socks5_proxies_to_test:
        all_results.extend(await run_tests(socks5_proxies_to_test, "socks5"))
    if socks4_proxies_to_test:
        all_results.extend(await run_tests(socks4_proxies_to_test, "socks4"))

    history = load_history()
    for proxy, scheme, lat, spd, sc, success in all_results:
        history[proxy].append((sc, success))
    save_history(history)

    rows = []
    for proxy, scheme, lat, spd, sc, success in all_results:
        entries = list(history[proxy])
        lt = sum(score for score, _ in entries) / len(entries) if entries else sc
        rr = sum(1 for _, succ in entries if succ)/len(entries)*100 if entries else (100.0 if success else 0.0)
        ss = [score for score, succ in entries if succ]
        ra = sum(ss)/len(ss) if ss else (sc if success else 0.0)
        status = "OK" if success else "FAILED"
        rows.append((proxy, scheme, lat, spd, sc, lt, rr, ra, status))

    sorted_rows = sorted(rows, key=lambda r: r[5], reverse=True)

    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Proxy","Protocol","Latency (s)","Speed (MB/s)",
            "Current Score","Long-Term Score",
            "Response Rate (%)","Response AVG","Status"
        ])
        for proxy, scheme, lat, spd, sc, lt, rr, ra, status in sorted_rows:
            writer.writerow([
                proxy, scheme,
                f"{lat:.3f}" if lat else "",
                f"{spd:.2f}" if spd else "",
                f"{sc:.2f}", f"{lt:.2f}",
                f"{rr:.1f}", f"{ra:.2f}", status
            ])

    mb_proxies_count = save_mb_proxies(sorted_rows)
    working_proxies_count = save_all_proxies(sorted_rows)

    elapsed = perf_counter() - t0
    print(f"\n=== BENCHMARK SUMMARY ===")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Original proxies: {total_proxies}")
    print(f"After deduplication: {total_proxies_after_dedup}")
    print(f"Pre-screening: Filtered {total_proxies_after_dedup - len(all_proxies_to_test)} dead proxies")
    print(f"Performance testing: {len(good)} good, {len(bad)} bad")
    if not sorted_rows:
        print("Warning: No proxies passed performance tests. Writing empty results.")
        with open(MB_PROXIES_FILE, "w") as f:
            f.write("# No proxies passed performance tests\n")
        with open(MB_PROXIES_ALL_FILE, "w") as f:
            f.write("# No proxies passed performance tests\n")
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Proxy","Protocol","Latency (s)","Speed (MB/s)",
                "Current Score","Long-Term Score",
                "Response Rate (%)","Response AVG"
            ])
        return
    print(f"Qualified proxies: {mb_proxies_count} → {MB_PROXIES_FILE}")
    print(f"Working proxies: {working_proxies_count} → {MB_PROXIES_ALL_FILE}")
    print(f"Detailed results: {CSV_FILE}")
    print(f"Proxy history: {HISTORY_FILE}")
    print(f"All output files are now saved to the '{OUTPUT_DIR}' folder")

if __name__ == "__main__":
    asyncio.run(main())
