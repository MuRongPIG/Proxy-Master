import sys
if sys.platform.startswith("win"):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
import asyncio
import csv
import os
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

TEST_URL            = "http://ipv4.download.thinkbroadband.com/100MB.zip"
CHUNK_RANGE         = "bytes=0-10485759"  # first 10 MB
TIMEOUT             = 10                  # seconds
CONCURRENT_LIMIT    = 512                 # max simultaneous tasks
HISTORY_MAX_RUNS    = 10                  # keep last N runs per proxy
MIN_TESTS_FOR_FAIL  = 3                   # threshold to consider continuous failures

# PERFORMANCE CUTOFF SETTINGS
MIN_SCORE_THRESHOLD = 0.5                 # Minimum score to be considered "good"
MIN_RESPONSE_RATE   = 1.0                # Minimum response rate percentage
MIN_PROXIES_COUNT   = 75                  # Minimum number of proxies to include

# PRE-SCREENING SETTINGS
PRE_SCREEN_URL      = "http://httpbin.org/ip"  # Lightweight test URL
PRE_SCREEN_TIMEOUT  = 5                   # Quick timeout for pre-screening
PRE_SCREEN_CONCURRENT = 512               # Concurrent limit for pre-screening

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
    return responsive_proxies

async def try_proxy(session, proxy: str, scheme: str) -> tuple:
    proxy_url = f"{scheme}://{proxy}"
    headers   = {"Range": CHUNK_RANGE}
    try:
        async with sem:
            start = perf_counter()
            async with session.get(TEST_URL, headers=headers, proxy=proxy_url, timeout=TIMEOUT) as resp:
                if resp.status not in (200, 206):
                    raise Exception(f"HTTP {resp.status}")
                total = 0
                async for chunk in resp.content.iter_chunked(65536):
                    total += len(chunk)
                    if total >= 10 * 1024 * 1024:
                        break
                elapsed = perf_counter() - start
                speed   = total / elapsed / 1024 / 1024
                latency = elapsed
                score   = speed / (latency + 0.01)
                good.append(proxy)
                return proxy, scheme, latency, speed, score, True
    except Exception:
        bad.append(proxy)
        return proxy, scheme, None, None, 0.0, False

async def run_tests(proxies: list, scheme: str):
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

def remove_duplicates(http_list: list, socks5_list: list, socks4_list: list) -> tuple:
    """Remove duplicate IP:port combinations, prioritizing SOCKS5 when duplicates exist."""
    print("Checking for duplicate IP:port combinations...")
    
    # Create sets of IP:port combinations for each protocol
    http_ips = set(http_list)
    socks5_ips = set(socks5_list)
    socks4_ips = set(socks4_list)
    
    # Find all unique IP:port combinations
    all_ips = http_ips | socks5_ips | socks4_ips
    
    # Track which protocol each IP:port came from originally
    ip_sources = {}
    for ip in http_ips:
        ip_sources[ip] = 'http'
    for ip in socks5_ips:
        ip_sources[ip] = 'socks5'
    for ip in socks4_ips:
        ip_sources[ip] = 'socks4'
    
    # Resolve duplicates by prioritizing SOCKS5
    final_http = []
    final_socks5 = []
    final_socks4 = []
    
    duplicates_found = 0
    
    for ip in all_ips:
        sources = []
        if ip in http_ips:
            sources.append('http')
        if ip in socks5_ips:
            sources.append('socks5')
        if ip in socks4_ips:
            sources.append('socks4')
        
        if len(sources) > 1:
            duplicates_found += 1
            # Prioritize SOCKS5, then HTTP, then SOCKS4
            if 'socks5' in sources:
                final_socks5.append(ip)
            elif 'http' in sources:
                final_http.append(ip)
            else:
                final_socks4.append(ip)
        else:
            # No duplicates, add to appropriate list
            protocol = sources[0]
            if protocol == 'http':
                final_http.append(ip)
            elif protocol == 'socks5':
                final_socks5.append(ip)
            else:  # socks4
                final_socks4.append(ip)
    
    if duplicates_found > 0:
        print(f"Found {duplicates_found} duplicate IP:port combinations")
        print(f"Duplicates resolved by prioritizing SOCKS5 > HTTP > SOCKS4")
    
    return final_http, final_socks5, final_socks4

def load_history():
    history = defaultdict(lambda: deque(maxlen=HISTORY_MAX_RUNS))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            reader = csv.DictReader(f)
            for row in reader:
                proxy = row['Proxy']
                score = float(row['Score'])
                success = row['Success'] == '1'
                history[proxy].append((score, success))
    return history

def save_history(history):
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Proxy", "Timestamp", "Score", "Success"])
        for proxy, entries in history.items():
            for score, success in entries:
                writer.writerow([proxy, int(time()), f"{score:.2f}", '1' if success else '0'])

def save_mb_proxies(sorted_rows):
    """Save the best performing proxies to MBProxies.txt in IP:port format."""
    # Filter proxies based on performance criteria
    qualified_proxies = []
    
    for proxy, scheme, lat, spd, sc, lt, rr, ra in sorted_rows:
        # Only include proxies that:
        # 1. Have a current score above threshold
        # 2. Have a good response rate
        # 3. Actually succeeded in the current test (have latency and speed data)
        if (sc >= MIN_SCORE_THRESHOLD and 
            rr >= MIN_RESPONSE_RATE and 
            lat is not None and spd is not None):
            qualified_proxies.append((proxy, sc))
    
    if not qualified_proxies:
        print("Warning: No proxies met the quality criteria!")
        return 0
    
    # Sort by score (best to worst)
    qualified_proxies.sort(key=lambda x: x[1], reverse=True)
    
    # Smart fallback approach: ensure minimum count while prioritizing quality
    total_qualified = len(qualified_proxies)
    
    if total_qualified >= MIN_PROXIES_COUNT:
        # We have enough qualified proxies, use only the qualified ones
        final_proxies = qualified_proxies
        print(f"Found {total_qualified} qualified proxies (above minimum {MIN_PROXIES_COUNT})")
        print(f"Including all {total_qualified} qualified proxies")
    else:
        # We don't have enough qualified proxies, need to include some fallback proxies
        print(f"Only {total_qualified} proxies met quality criteria (below minimum {MIN_PROXIES_COUNT})")
        print(f"Adding fallback proxies to reach minimum {MIN_PROXIES_COUNT}")
        
        # Start with all qualified proxies
        final_proxies = qualified_proxies.copy()
        
        # Find additional proxies that succeeded in testing but didn't meet quality thresholds
        fallback_proxies = []
        for proxy, scheme, lat, spd, sc, lt, rr, ra in sorted_rows:
            # Include proxies that succeeded in testing (have latency/speed data) but don't meet quality thresholds
            if (proxy not in [p[0] for p in final_proxies] and  # Not already included
                lat is not None and spd is not None):  # Succeeded in current test
                fallback_proxies.append((proxy, sc))
        
        # Sort fallback proxies by score (best to worst)
        fallback_proxies.sort(key=lambda x: x[1], reverse=True)
        
        # Add fallback proxies until we reach the minimum
        needed_fallback = MIN_PROXIES_COUNT - total_qualified
        fallback_to_add = fallback_proxies[:needed_fallback]
        
        final_proxies.extend(fallback_to_add)
        
        print(f"Added {len(fallback_to_add)} fallback proxies (total: {len(final_proxies)})")
        print(f"Fallback proxies don't meet strict quality criteria but succeeded in testing")
    
    # Save to MBProxies.txt (IP:port format only)
    with open(MB_PROXIES_FILE, "w") as f:
        for proxy, score in final_proxies:
            f.write(f"{proxy}\n")
    
    print(f"Saved {len(final_proxies)} proxies to {MB_PROXIES_FILE}")
    print(f"Quality criteria: Score >= {MIN_SCORE_THRESHOLD}, Response rate >= {MIN_RESPONSE_RATE}%")
    print(f"Result: {len(final_proxies)} proxies included (ensuring minimum {MIN_PROXIES_COUNT})")
    
    return len(final_proxies)

async def main():
    print("Starting proxy benchmark...")
    print(f"Loading proxies from: {PROXY_FILE_HTTP}, {PROXY_FILE_SOCKS5}, {PROXY_FILE_SOCKS4}")
    
    # Ensure output directory exists
    ensure_output_directory()
    
    t0 = perf_counter()
    http_list   = load_proxies(PROXY_FILE_HTTP)
    socks5_list = load_proxies(PROXY_FILE_SOCKS5)
    socks4_list = load_proxies(PROXY_FILE_SOCKS4)

    total_proxies = len(http_list) + len(socks5_list) + len(socks4_list)
    if total_proxies == 0:
        print("No proxies found! Make sure getproxy.py has been run first.")
        return
    
    print(f"Loaded {len(http_list)} HTTP, {len(socks5_list)} SOCKS5, {len(socks4_list)} SOCKS4 proxies")
    print(f"Total proxies loaded: {total_proxies}")

    # Remove duplicate IP:port combinations
    http_list, socks5_list, socks4_list = remove_duplicates(http_list, socks5_list, socks4_list)
    
    total_proxies_after_dedup = len(http_list) + len(socks5_list) + len(socks4_list)
    print(f"After removing duplicates: {len(http_list)} HTTP, {len(socks5_list)} SOCKS5, {len(socks4_list)} SOCKS4 proxies")
    print(f"Total proxies after deduplication: {total_proxies_after_dedup}")

    # Pre-screen proxies to filter out dead ones
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
        all_results += await run_tests(http_proxies_to_test, "http")
    if socks5_proxies_to_test:
        all_results += await run_tests(socks5_proxies_to_test, "socks5")
    if socks4_proxies_to_test:
        all_results += await run_tests(socks4_proxies_to_test, "socks4")

    history = load_history()
    for proxy, scheme, lat, spd, sc, success in all_results:
        history[proxy].append((sc, success))
    save_history(history)

    # Prepare CSV rows
    rows = []
    for proxy, scheme, lat, spd, sc, success in all_results:
        entries = list(history[proxy])
        lt = sum(score for score, _ in entries) / len(entries) if entries else sc
        rr = sum(1 for _, succ in entries if succ)/len(entries)*100 if entries else (100.0 if success else 0.0)
        ss = [score for score, succ in entries if succ]
        ra = sum(ss)/len(ss) if ss else 0.0
        rows.append((proxy, scheme, lat, spd, sc, lt, rr, ra))

    sorted_rows = sorted(rows, key=lambda r: r[5], reverse=True)

    # Save detailed CSV results
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Proxy","Protocol","Latency (s)","Speed (MB/s)",
            "Current Score","Long-Term Score",
            "Response Rate (%)","Response AVG"
        ])
        for proxy, scheme, lat, spd, sc, lt, rr, ra in sorted_rows:
            writer.writerow([
                proxy, scheme,
                f"{lat:.3f}" if lat else "",
                f"{spd:.2f}" if spd else "",
                f"{sc:.2f}", f"{lt:.2f}",
                f"{rr:.1f}", f"{ra:.2f}"
            ])

    # Save MBProxies.txt with best performing proxies
    mb_proxies_count = save_mb_proxies(sorted_rows)

    elapsed = perf_counter() - t0
    print(f"\n=== BENCHMARK SUMMARY ===")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Original proxies: {total_proxies}")
    print(f"After deduplication: {total_proxies_after_dedup}")
    print(f"Pre-screening: Filtered {total_proxies_after_dedup - len(all_proxies_to_test)} dead proxies from {total_proxies_after_dedup} total")
    print(f"Performance testing: {len(good)} good, {len(bad)} bad")
    print(f"Qualified proxies: {mb_proxies_count} → {MB_PROXIES_FILE}")
    print(f"Detailed results: {CSV_FILE}")
    print(f"Proxy history: {HISTORY_FILE}")
    print(f"All output files are now saved to the '{OUTPUT_DIR}' folder")

if __name__ == "__main__":
    asyncio.run(main())
