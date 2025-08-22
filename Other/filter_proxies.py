import os
import csv
import requests
import concurrent.futures
import time
from typing import List, Tuple
import multiprocessing

# Configuration
TEST_URL = "https://httpbin.org/ip"  # Recommended lightweight endpoint
TIMEOUT = 3
MAX_WORKERS = 512

# Input files by protocol
PROXY_SOURCES = {
    "http": "http.txt",
    "socks4": "socks4.txt",
    "socks5": "socks5.txt"
}


def read_unique_proxies(file_path: str) -> List[str]:
    seen = set()
    proxies = []
    if not os.path.exists(file_path):
        return proxies
    with open(file_path, "r") as f:
        for line in f:
            proxy = line.strip()
            if proxy and proxy not in seen:
                seen.add(proxy)
                proxies.append(proxy)
    return proxies


def test_proxy(proxy: str, protocol: str) -> Tuple[str, float]:
    proxy_url = f"{protocol}://{proxy}"
    try:
        start = time.time()
        r = requests.get(TEST_URL, proxies={"http": proxy_url, "https": proxy_url}, timeout=TIMEOUT)
        if r.status_code == 200:
            latency = round((time.time() - start) * 1000, 2)  # ms
            return proxy, latency
    except:
        pass
    return proxy, None


def filter_and_test_proxies(protocol: str, proxy_list: List[str]) -> List[Tuple[str, float]]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(test_proxy, proxy, protocol): proxy for proxy in proxy_list}
        for future in concurrent.futures.as_completed(futures):
            proxy, latency = future.result()
            if latency is not None:
                results.append((proxy, latency))
    return results


def save_csv_output(filtered_proxies: dict):
    output_file = "filtered_proxies.csv"
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["HTTP Proxy", "Latency (ms)", "", "SOCKS4 Proxy", "Latency (ms)", "", "SOCKS5 Proxy", "Latency (ms)"])

        max_len = max(len(filtered_proxies.get("http", [])), len(filtered_proxies.get("socks4", [])), len(filtered_proxies.get("socks5", [])))
        for i in range(max_len):
            row = []
            for proto in ["http", "socks4", "socks5"]:
                entries = filtered_proxies.get(proto, [])
                if i < len(entries):
                    proxy, latency = entries[i]
                    row.extend([proxy, latency])
                else:
                    row.extend(["", ""])
                row.append("")  # spacer
            writer.writerow(row)


if __name__ == "__main__":
    filtered_proxies = {}
    for proto, path in PROXY_SOURCES.items():
        print(f"Loading {proto.upper()} proxies from {path}...")
        proxies = read_unique_proxies(path)
        print(f"{len(proxies)} unique {proto.upper()} proxies loaded. Testing...")
        tested = filter_and_test_proxies(proto, proxies)
        print(f"{len(tested)} {proto.upper()} proxies responded.")
        filtered_proxies[proto] = tested

    save_csv_output(filtered_proxies)
    print("[✓] Proxy filtering and testing complete. Results saved to filtered_proxies.csv.")
