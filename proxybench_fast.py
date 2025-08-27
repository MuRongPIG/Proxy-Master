#!/usr/bin/env python3
# proxybench_fast.py — stripped, fast proxy weed-out + light ranking
#
# Purpose:
#   - Extremely fast CI pass to find working, low-latency, reasonably quick proxies.
#   - No MEGA stage, no pacing, no gzip, no streaming CSV.
#
# Deps:
#   pip install "httpx[socks]" tqdm
#
# Env (defaults tuned for speed):
#   INPUT_DIR="."                 OUTPUT_DIR="Output"
#   CONNECT_TIMEOUT_S="2.0"       READ_TIMEOUT_S="2.5"
#   A_SAMPLE_BYTES="16384"        # tiny read for latency check (~16 KiB)
#   B_SAMPLE_BYTES="256000"       # ~0.244 MiB cap
#   B_MAX_DURATION_S="2.5"
#   WORKERS="300"                 PER_HOST_LIMIT="32"
#   THR_WEIGHT="0.001"            LAT_PENALTY="0.25"
#   MIN_COUNT="75"                SCORE_THRESHOLD="40.0"
#   SHUFFLE_INPUT="1"             CROSS_PROTO_DEDUP="1"
#   CSV_NAME="MBProxies.csv"
#   LATENCY_SKIP_MS="850"         # skip Stage-B if Stage-A is too slow
#
# Inputs:
#   socks5.txt, http.txt (http+https proxies), socks4.txt in INPUT_DIR
#
# Outputs:
#   Output/MBProxiesAll.txt (ranked working proxies: host:port)
#   Output/MBProxies.txt (top N by score with threshold/backfill)
#   Output/MBProxies.csv (all tested with metrics)

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Union, Iterable
import ipaddress
import csv
from statistics import median
from urllib.parse import quote

import httpx
from tqdm import tqdm

# ---------------- Config ----------------
INPUT_DIR = os.environ.get("INPUT_DIR", ".")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "Output")

INPUT_FILES = {
    "socks5": os.path.join(INPUT_DIR, "socks5.txt"),
    "http":   os.path.join(INPUT_DIR, "http.txt"),
    "socks4": os.path.join(INPUT_DIR, "socks4.txt"),
}

CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "2.0"))
READ_TIMEOUT_S    = float(os.environ.get("READ_TIMEOUT_S", "2.5"))
A_SAMPLE_BYTES    = int(os.environ.get("A_SAMPLE_BYTES", "16384"))
B_SAMPLE_BYTES    = int(os.environ.get("B_SAMPLE_BYTES", "256000"))
B_MAX_DURATION_S  = float(os.environ.get("B_MAX_DURATION_S", "2.5"))

WORKERS        = int(os.environ.get("WORKERS", "300"))
PER_HOST_LIMIT = int(os.environ.get("PER_HOST_LIMIT", "32"))

THR_WEIGHT      = float(os.environ.get("THR_WEIGHT", "0.001"))
LAT_PENALTY     = float(os.environ.get("LAT_PENALTY", "0.25"))
MIN_COUNT       = int(os.environ.get("MIN_COUNT", "75"))
SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "40.0"))

SHUFFLE_INPUT     = os.environ.get("SHUFFLE_INPUT", "1") == "1"
CROSS_PROTO_DEDUP = os.environ.get("CROSS_PROTO_DEDUP", "1") == "1"
CSV_NAME          = os.environ.get("CSV_NAME", "MBProxies.csv")

LATENCY_SKIP_MS   = float(os.environ.get("LATENCY_SKIP_MS", "850"))

PROTO_PRIORITY = {"socks5": 3, "http": 2, "socks4": 1}
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "KHTML, like Gecko) Chrome/119.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

# ---------------- Helpers ----------------
def parse_line(line: str) -> Optional[Tuple[str, int, Optional[str], Optional[str]]]:
    s = line.strip()
    if not s or s.startswith("#"): return None
    user = pw = None
    hostport = s
    if "@" in s:
        auth, hostport = s.rsplit("@", 1)
        if ":" in auth: user, pw = auth.split(":", 1)
        else: user, pw = auth, ""
    if hostport.startswith("["):
        try:
            r = hostport.index("]")
            host = hostport[1:r]
            if hostport[r+1:r+2] != ":": return None
            port = int(hostport[r+2:])
        except Exception:
            return None
    else:
        parts = hostport.split(":")
        if len(parts) != 2: return None
        host, ps = parts
        try: port = int(ps)
        except: return None
    if not (1 <= port <= 65535): return None
    try:
        ipaddress.ip_address(host)
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
            seen = set()
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    rec = parse_line(line)
                    if not rec: continue
                    h, pt, user, pw = rec
                    hp = (h, pt)
                    if hp in seen: continue
                    seen.add(hp)
                    if hp not in merged or PROTO_PRIORITY[proto] > PROTO_PRIORITY[ merged[hp][0] ]:
                        merged[hp] = (proto, user, pw)
        return merged
    else:
        merged3: Dict[Tuple[str,int,str], Tuple[Optional[str], Optional[str]]] = {}
        for proto, path in INPUT_FILES.items():
            p = Path(path)
            if not p.exists(): continue
            seen = set()
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    rec = parse_line(line)
                    if not rec: continue
                    h, pt, user, pw = rec
                    hp = (h, pt)
                    if hp in seen: continue
                    seen.add(hp)
                    merged3[(h, pt, proto)] = (user, pw)
        return merged3

def proxy_url_candidates(proto: str, host: str, port: int, user: Optional[str], pw: Optional[str]) -> List[str]:
    auth = ""
    if user is not None:
        auth = f"{quote(user, safe='')}:{quote(pw or '', safe='')}@"
    if proto == "socks5":
        return [f"socks5h://{auth}{host}:{port}"]  # remote DNS
    if proto == "socks4":
        return [f"socks4://{auth}{host}:{port}"]
    # http list can include HTTPS proxies; try both
    return [f"http://{auth}{host}:{port}", f"https://{auth}{host}:{port}"]

def fmt_hostport(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["): return f"[{host}]:{port}"
    return f"{host}:{port}"

# ---------------- Benchmark ----------------
class BenchResult:
    __slots__ = ("host","port","proto","ok","latency_ms","thr_bps","score")
    def __init__(self, host, port, proto):
        self.host=host; self.port=port; self.proto=proto
        self.ok=False; self.latency_ms=None; self.thr_bps=0.0; self.score=-1e9
    def calc_score(self):
        if self.latency_ms is None or self.thr_bps<=0: self.score=-1e9; return
        self.score=(self.thr_bps*THR_WEIGHT)-(self.latency_ms*LAT_PENALTY)

async def stage_a(client: httpx.AsyncClient, proxies: Iterable[str]) -> Tuple[bool, Optional[float], Optional[str]]:
    # Use two generic targets to avoid localized issues
    urls = (
        "https://cachefly.cachefly.net/1mb.test",
        "https://speed.hetzner.de/1MB.bin",
    )
    for pxy in proxies:
        for url in urls:
            t0=time.perf_counter()
            try:
                async with client.stream(
                    "GET", url,
                    headers=BROWSER_HEADERS,
                    timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=CONNECT_TIMEOUT_S),
                    proxies=pxy
                ) as resp:
                    if resp.status_code>=400: raise httpx.HTTPStatusError("bad status", request=resp.request, response=resp)
                    total=0
                    async for chunk in resp.aiter_bytes():
                        total+=len(chunk)
                        if total>=A_SAMPLE_BYTES:
                            return True, (time.perf_counter()-t0)*1000.0, pxy
            except Exception:
                pass
    return False, None, None

async def stage_b(client: httpx.AsyncClient, proxy: str) -> float:
    url="https://cachefly.cachefly.net/10mb.test"
    start=time.perf_counter(); got=0
    try:
        async with client.stream(
            "GET", url,
            headers=BROWSER_HEADERS,
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=B_MAX_DURATION_S+0.5, write=CONNECT_TIMEOUT_S),
            proxies=proxy
        ) as resp:
            if resp.status_code>=400: return 0.0
            async for chunk in resp.aiter_bytes():
                got+=len(chunk)
                if got>=B_SAMPLE_BYTES or (time.perf_counter()-start)>=B_MAX_DURATION_S:
                    break
    except Exception:
        return 0.0
    dur=max(1e-6, time.perf_counter()-start)
    return got/dur

async def worker(q: asyncio.Queue, out: List[BenchResult], client: httpx.AsyncClient, pbar: tqdm):
    while True:
        item=await q.get()
        if item is None:
            q.task_done(); return
        host,port,proto,user,pw=item
        br=BenchResult(host,port,proto)
        candidates=proxy_url_candidates(proto,host,port,user,pw)

        ok,lat,pxy=await stage_a(client,candidates)
        if ok and lat is not None:
            br.latency_ms=lat
            thr=0.0
            if lat<=LATENCY_SKIP_MS:
                thr=await stage_b(client,pxy)
            br.thr_bps=thr
            if thr>0:
                br.ok=True
                br.calc_score()
        out.append(br)
        pbar.update(1)
        q.task_done()

async def run(proxies: List[Tuple[str,int,str,Optional[str],Optional[str]]]) -> List[BenchResult]:
    results: List[BenchResult]=[]
    limits=httpx.Limits(max_connections=WORKERS, max_keepalive_connections=PER_HOST_LIMIT)
    async with httpx.AsyncClient(http2=False, limits=limits, verify=True, trust_env=False) as client:
        q: asyncio.Queue=asyncio.Queue()
        for host,port,proto,user,pw in proxies:
            q.put_nowait((host,port,proto,user,pw))
        for _ in range(WORKERS):
            q.put_nowait(None)
        with tqdm(total=len(proxies), desc="Fast bench", unit="proxy", mininterval=0.2) as pbar:
            tasks=[asyncio.create_task(worker(q,results,client,pbar)) for _ in range(WORKERS)]
            await q.join()
            for t in tasks: await t
    return results

# --------------- Output ----------------
def write_outputs(results: List[BenchResult], duration_s: float, total: int):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    good=[r for r in results if r.ok]
    good.sort(key=lambda r:r.score, reverse=True)

    all_path=Path(OUTPUT_DIR)/"MBProxiesAll.txt"
    with all_path.open("w", encoding="utf-8") as f:
        for r in good:
            f.write(f"{fmt_hostport(r.host,r.port)}\n")

    selected=[r for r in good if r.score>=SCORE_THRESHOLD]
    if len(selected)<MIN_COUNT:
        ids=set((r.host,r.port) for r in selected)
        for r in good:
            if len(selected)>=MIN_COUNT: break
            k=(r.host,r.port)
            if r.score<SCORE_THRESHOLD and k not in ids:
                selected.append(r); ids.add(k)

    mb_path=Path(OUTPUT_DIR)/"MBProxies.txt"
    with mb_path.open("w", encoding="utf-8") as f:
        for r in selected[:MIN_COUNT]:
            f.write(f"{fmt_hostport(r.host,r.port)}\n")

    csv_path=Path(OUTPUT_DIR)/CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["host","port","proto","ok","latency_ms","thr_bps","score"])
        for r in results:
            w.writerow([
                r.host, r.port, r.proto, int(r.ok),
                0 if r.latency_ms is None else round(r.latency_ms,3),
                round(r.thr_bps,1),
                round(r.score,3),
            ])

    processed_per_sec = total / max(1e-6, duration_s)
    ok_count=len(good)
    lat=[r.latency_ms for r in good if r.latency_ms is not None]
    thr=[r.thr_bps for r in good if r.thr_bps>0]
    print("\n=== Fast Benchmark Summary ===")
    print(f"Time: {duration_s:.2f}s  Tested: {total}  Proc/s: {processed_per_sec:.2f}")
    print(f"Responsive: {ok_count} ({(ok_count/total*100 if total else 0):.2f}%)")
    if good:
        print(f"Top score: {good[0].score:.2f} ({fmt_hostport(good[0].host,good[0].port)} / {good[0].proto})")
    if lat: print(f"Median latency: {median(lat):.1f} ms")
    if thr: print(f"Median throughput: {median(thr):.0f} B/s")
    print(f"Selected for MBProxies.txt: {min(MIN_COUNT,len(selected))}/{MIN_COUNT} (threshold {SCORE_THRESHOLD})")
    print(f"Outputs: {all_path}, {mb_path}, {csv_path}")

# --------------- Main ----------------
def main():
    merged=load_and_dedupe()
    if not merged:
        print("No proxies found.", file=sys.stderr); sys.exit(1)

    if CROSS_PROTO_DEDUP:
        items=[(h,p, merged[(h,p)][0], merged[(h,p)][1], merged[(h,p)][2]) for (h,p) in merged.keys()]
    else:
        items=[(h,p, proto, merged[(h,p,proto)][0], merged[(h,p,proto)][1]) for (h,p,proto) in merged.keys()]

    if SHUFFLE_INPUT:
        try:
            import random as _r; _r.shuffle(items)
        except Exception: pass

    t0=time.perf_counter()
    results=asyncio.run(run(items))
    duration=time.perf_counter()-t0
    write_outputs(results, duration, total=len(items))

if __name__=="__main__":
    main()
