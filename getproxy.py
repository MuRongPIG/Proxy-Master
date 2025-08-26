#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Proxy collector:
- Scrapes many plaintext/HTML sources
- Pulls rotating JSON proxies from getproxylist.com (one proxy per request, filtered)
- Paginates GeoNode's free JSON list
- Dedupes within each protocol bucket (HTTP, SOCKS4, SOCKS5), but allows multi-protocol duplicates
- Writes http.txt, socks4.txt, socks5.txt and a consolidated ProxyList.csv

Python 3.9+ recommended
"""

import time
import datetime
import requests
import re
import csv
from datetime import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# ===================== Tunables =====================

# Try to import configuration file, fall back to defaults
try:
    from getproxy_config import *
    print("📋 Loaded configuration from getproxy_config.py")
except ImportError:
    print("⚠️ No configuration file found, using default settings")
    # Default values if no config file
    SKIP_JSON_ROTATORS = False
    MAX_ATTEMPTS_MULTIPLIER = 3
    MAX_CONSECUTIVE_FAILURES = 10
    COLLECTION_TIMEOUT = 1800

# getproxylist.com (JSON rotator) controls
GPL_REQUESTS_PER_PROTOCOL = getattr(locals(), 'GPL_REQUESTS_PER_PROTOCOL', 400)
GPL_LAST_TESTED_SEC = getattr(locals(), 'GPL_LAST_TESTED_SEC', 900)
GPL_MIN_UPTIME = getattr(locals(), 'GPL_MIN_UPTIME', 80)
GPL_MIN_DL_BPS = getattr(locals(), 'GPL_MIN_DL_BPS', 1000)
GPL_MAX_CONNECT_S = getattr(locals(), 'GPL_MAX_CONNECT_S', 2)
GPL_PER_REQUEST_SLEEP = getattr(locals(), 'GPL_PER_REQUEST_SLEEP', 0.05)
GPL_RETRIES = getattr(locals(), 'GPL_RETRIES', 3)
GPL_BACKOFF_BASE = getattr(locals(), 'GPL_BACKOFF_BASE', 0.6)
GPL_API_KEY: Optional[str] = getattr(locals(), 'GPL_API_KEY', None)

# GeoNode pagination controls
GEONODE_LIMIT_PER_PAGE = getattr(locals(), 'GEONODE_LIMIT_PER_PAGE', 500)
GEONODE_MAX_PAGES = getattr(locals(), 'GEONODE_MAX_PAGES', 50)

# HTTP client defaults
REQUEST_TIMEOUT = getattr(locals(), 'REQUEST_TIMEOUT', 8)
UA = "ProxyCollector/1.3 (+https://github.com/you) requests/2.x"

# ====================================================


class DownloadProxies:
    """
    Scrape free proxy lists, dedupe by protocol, write .txt files and
    a consolidated CSV (ProxyList.csv) with a timestamp and counts.
    """
    def __init__(self) -> None:
        # Plaintext/HTML sources returning many proxies per request
        self.api_text: Dict[str, List[str]] = {
            'socks4': [
                "https://api.proxyscrape.com/?request=displayproxies&proxytype=socks4&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=socks4",
                "https://api.openproxylist.xyz/socks4.txt",
                "https://proxyspace.pro/socks4.txt",
                "https://sunny9577.github.io/proxy-scraper/generated/socks4_proxies.txt",
                "https://openproxy.space/list/socks4",
                "https://cdn.rei.my.id/proxy/SOCKS4",
                "https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/socks4.txt",
                "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
                "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt",
                "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt",
                "https://raw.githubusercontent.com/Noctiro/getproxy/master/file/socks4.txt",
                "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks4.txt",
                "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/socks4.txt",
                "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks4.txt",
                "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt",
                "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt",
                "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt",
            ],
            'socks5': [
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=socks5",
                "https://api.openproxylist.xyz/socks5.txt",
                "https://openproxy.space/list/socks5",
                "https://spys.me/socks.txt",
                "https://proxyspace.pro/socks5.txt",
                "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
                "https://cdn.rei.my.id/proxy/SOCKS5",
                "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
                "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
                "https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/socks5.txt",
                "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks5_proxies.txt",
                "https://raw.githubusercontent.com/Noctiro/getproxy/master/file/socks5.txt",
                "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt",
                "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/socks5.txt",
                "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks5.txt",
                "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
                "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
            ],
            'http': [
                "https://api.proxyscrape.com/?request=displayproxies&proxytype=http&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=http",
                "https://www.proxy-list.download/api/v1/get?type=https",
                "https://spys.me/proxy.txt",
                "https://api.openproxylist.xyz/http.txt",
                "https://openproxy.space/list/http",
                "https://proxyspace.pro/http.txt",
                "https://proxyspace.pro/https.txt",
                "https://sunny9577.github.io/proxy-scraper/generated/http_proxies.txt",
                "https://cdn.rei.my.id/proxy/HTTP",
                "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
                "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
                "https://github.com/monosans/proxy-list/raw/main/proxies/http.txt",
                "https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/http.txt",
                "https://github.com/mmpx12/proxy-list/raw/master/http.txt",
                "https://github.com/mmpx12/proxy-list/raw/master/https.txt",
                "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
                "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/https_proxies.txt",
                "https://raw.githubusercontent.com/Noctiro/getproxy/master/file/http.txt",
                "https://raw.githubusercontent.com/Noctiro/getproxy/master/file/https.txt",
                "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
                "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/http.txt",
                "https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/http.txt",
                "https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/https.txt",
                "https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/http.txt",
                "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http.txt",
                "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/https.txt",
                "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/http.txt",
                "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/http.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
                "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
                "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
                "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
                "https://raw.githubusercontent.com/aslisk/proxyhttps/main/https.txt",
                "https://raw.githubusercontent.com/saisuiu/uiu/main/free.txt",
                "https://raw.githubusercontent.com/berkay-digital/Proxy-Scraper/main/proxies.txt",
                "https://raw.githubusercontent.com/MrMarble/proxy-list/main/all.txt",
            ],
        }

        # JSON rotators (one proxy per request). Map protocol -> list of (url, fixed_params)
        self.api_json: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {
            "http":   [("https://api.getproxylist.com/proxy", {"protocol": "http"})],
            "socks4": [("https://api.getproxylist.com/proxy", {"protocol": "socks4"})],
            "socks5": [("https://api.getproxylist.com/proxy", {"protocol": "socks5"})],
        }

        self.proxy_dict = {'socks4': set(), 'socks5': set(), 'http': set()}

        # shared session
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})

    # ----------------------------- helpers ---------------------------------
    @staticmethod
    def _extract_ipports(text: str) -> List[str]:
        # Simple IPv4:port; avoids overmatching hostnames
        return re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b", text)

    def _get_with_retries(self, url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
        for attempt in range(1, 4):
            try:
                r = self.session.get(url, timeout=timeout)
                if r.status_code == 200:
                    return r.text
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(0.5 * attempt)
                    continue
                return None
            except requests.RequestException:
                time.sleep(0.4 * attempt)
        return None

    def _get_json_with_retries(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for attempt in range(1, GPL_RETRIES + 1):
            try:
                r = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(GPL_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                return None
            except requests.RequestException:
                time.sleep(GPL_BACKOFF_BASE * (2 ** (attempt - 1)))
        return None

    # ----------------------------- site-specific ---------------------------
    @staticmethod
    def _scrape_socksnet() -> List[str]:
        """Extract SOCKS4 proxies from https://www.socks-proxy.net/ (HTML table)."""
        try:
            html = requests.get("https://www.socks-proxy.net/", timeout=REQUEST_TIMEOUT).text
            tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
            if not tbody:
                return []
            rows = re.findall(r"<tr><td>(.*?)</td><td>(\d+)</td>", tbody.group(1))
            return [f"{ip}:{port}" for ip, port in rows]
        except Exception:
            return []

    def _scrape_checkerproxy_archive(self) -> None:
        """Append proxies from checkerproxy.net archive for last 10 days (generic strings)."""
        today = datetime.date.today()
        for offset in range(10):
            day = today - datetime.timedelta(days=offset)
            url = f"https://api.checkerproxy.net/v1/landing/archive/{day:%Y-%m-%d}"
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                data = resp.json().get("data", {}).get("proxyList", [])
                targets = data if isinstance(data, list) else list(data.values())
                for proxy in targets:
                    if isinstance(proxy, str):
                        m = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b", proxy)
                        if m:
                            ipport = m.group(0)
                            # we don’t know exact protocol; place into plausible buckets
                            self.proxy_dict["http"].add(ipport)
                            self.proxy_dict["socks5"].add(ipport)
            except Exception:
                continue

    # ----------------------------- collectors ------------------------------
    def _collect_text_sources(self) -> None:
        total_sources = sum(len(v) for v in self.api_text.values())
        idx = 0
        print(f"🌐 Scraping {total_sources} plaintext/HTML sources...")
        for proto, urls in self.api_text.items():
            print(f"\n📥 {proto.upper()} ({len(urls)} sources)")
            for url in urls:
                idx += 1
                host = url.split("//", 1)[-1].split("/", 1)[0]
                print(f"   [{idx}/{total_sources}] {host} ... ", end="")
                text = self._get_with_retries(url)
                if not text:
                    print("❌")
                    continue
                found = self._extract_ipports(text)
                before = len(self.proxy_dict[proto])
                self.proxy_dict[proto].update(found)
                print(f"✅ +{len(self.proxy_dict[proto]) - before}")

    def _collect_json_rotators(self) -> None:
        if SKIP_JSON_ROTATORS:
            print("⚠️ Skipping JSON rotators (getproxylist.com) due to SKIP_JSON_ROTATORS=True")
            return

        print("\n🔁 Scraping JSON rotators (getproxylist.com)...")
        base_filters = {
            "lastTested": GPL_LAST_TESTED_SEC,
            "minUptime": GPL_MIN_UPTIME,
            "minDownloadSpeed": GPL_MIN_DL_BPS,
            "maxConnectTime": GPL_MAX_CONNECT_S,
        }
        if GPL_API_KEY:
            base_filters["apiKey"] = GPL_API_KEY

        for proto, entries in self.api_json.items():
            print(f"   • {proto.upper()} via JSON (target unique adds ≈ {GPL_REQUESTS_PER_PROTOCOL} per entry)")
            for base_url, fixed_params in entries:
                unique_added = 0
                seen_attempts = 0
                max_attempts = GPL_REQUESTS_PER_PROTOCOL * MAX_ATTEMPTS_MULTIPLIER  # Safety limit: max attempts
                consecutive_failures = 0
                max_consecutive_failures = MAX_CONSECUTIVE_FAILURES  # Stop if consecutive failures
                
                while unique_added < GPL_REQUESTS_PER_PROTOCOL and seen_attempts < max_attempts:
                    params = dict(base_filters)
                    params.update(fixed_params)

                    data = self._get_json_with_retries(base_url, params)
                    seen_attempts += 1
                    
                    if not data:
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            print(f"     - {base_url}: Stopping due to {consecutive_failures} consecutive failures")
                            break
                        # backoff handled in helper; keep trying
                        continue
                    
                    # Reset consecutive failures counter on success
                    consecutive_failures = 0

                    ip = data.get("ip")
                    port = data.get("port")
                    if ip and port:
                        ipport = f"{ip}:{port}"
                        before = len(self.proxy_dict[proto])
                        self.proxy_dict[proto].add(ipport)
                        if len(self.proxy_dict[proto]) > before:
                            unique_added += 1

                    time.sleep(GPL_PER_REQUEST_SLEEP)

                print(f"     - {base_url}: +{unique_added} unique {proto} (attempts={seen_attempts})")
                if seen_attempts >= max_attempts:
                    print(f"       ⚠️  Reached maximum attempts limit ({max_attempts})")
                if consecutive_failures >= max_consecutive_failures:
                    print(f"       ⚠️  Stopped due to consecutive failures ({consecutive_failures})")

    def _collect_geonode_free(self, limit_per_page: int = GEONODE_LIMIT_PER_PAGE,
                              max_pages: int = GEONODE_MAX_PAGES) -> None:
        """
        Pull free proxies via GeoNode's JSON feed, paginate, and
        bucket into http/socks4/socks5 sets. Allows duplicates across protocols.
        """
        base_url = "https://proxylist.geonode.com/api/proxy-list"
        
        # Validate API limits
        if limit_per_page > 500:
            print(f"   ⚠️  API limit exceeded: {limit_per_page} > 500, reducing to 500")
            limit_per_page = 500
        
        params_base = {
            "limit": limit_per_page,
            "sort_by": "lastChecked",
            "sort_type": "desc",
            # Optional filters you can enable/tune:
            # "lastChecked": "900",                # seconds since last check
            # "uptime": "90",                      # >= % uptime
            # "speed": "fast,medium",              # or include "slow"
            # "anonymityLevel": "elite,anonymous,transparent",
            # "country": "US",                     # ISO 3166-1 alpha-2
            # "protocols": "http,https,socks4,socks5",
        }

        print(f"\n🛰️  Scraping GeoNode free proxy list (JSON, paginated)...")
        print(f"   📊 Settings: {limit_per_page} per page, max {max_pages} pages")
        print(f"   🎯 Expected max: {limit_per_page * max_pages:,} proxies")
        
        total_added = {"http": 0, "socks4": 0, "socks5": 0}
        total_processed = 0
        total_filtered = 0

        for page in range(1, max_pages + 1):
            params = dict(params_base)
            params["page"] = page

            print(f"   📄 Fetching page {page}...", end=" ")
            data = self._get_json_with_retries(base_url, params)
            
            if not data:
                print("❌ No response data")
                break
                
            if "data" not in data:
                print(f"❌ No 'data' field in response")
                if "message" in data:
                    print(f"   API message: {data['message']}")
                break
                
            if not isinstance(data["data"], list):
                print(f"❌ 'data' is not a list")
                break

            batch = data["data"]
            if not batch:
                print("📭 Empty batch (end of data)")
                break

            print(f"✅ Got {len(batch)} proxies")
            
            # Show API metadata if available
            if page == 1 and "total" in data:
                print(f"   📈 API reports total: {data['total']} proxies")
            if page == 1 and "page" in data:
                print(f"   📊 API page info: {data['page']}")

            added_this_page = {"http": 0, "socks4": 0, "socks5": 0}
            page_processed = 0
            page_filtered = 0
            
            for item in batch:
                page_processed += 1
                ip = item.get("ip")
                port = item.get("port")
                
                if not ip or not port:
                    page_filtered += 1
                    continue

                ipport = f"{ip}:{port}"

                # Prefer list under 'protocols'; fallback to single 'protocol'
                protos = item.get("protocols") or [item.get("protocol")]
                if not protos:
                    page_filtered += 1
                    continue

                for proto in protos:
                    if not proto:
                        continue
                    p = proto.lower()
                    if p in ("http", "https"):
                        before = len(self.proxy_dict["http"])
                        self.proxy_dict["http"].add(ipport)
                        added_this_page["http"] += len(self.proxy_dict["http"]) - before
                    elif p == "socks4":
                        before = len(self.proxy_dict["socks4"])
                        self.proxy_dict["socks4"].add(ipport)
                        added_this_page["socks4"] += len(self.proxy_dict["socks4"]) - before
                    elif p == "socks5":
                        before = len(self.proxy_dict["socks5"])
                        self.proxy_dict["socks5"].add(ipport)
                        added_this_page["socks5"] += len(self.proxy_dict["socks5"]) - before

            total_processed += page_processed
            total_filtered += page_filtered

            for k in total_added:
                total_added[k] += added_this_page[k]

            print(f"   • Page {page}: +HTTP {added_this_page['http']:4d}  "
                  f"+SOCKS4 {added_this_page['socks4']:4d}  +SOCKS5 {added_this_page['socks5']:4d}")
            print(f"     Processed: {page_processed}, Filtered: {page_filtered}")

            # Stop early if we received a short page (< limit), meaning likely last page
            if len(batch) < limit_per_page:
                print("   • Last page reached (short batch).")
                break

        print(f"   ✅ GeoNode totals — HTTP {total_added['http']}, "
              f"SOCKS4 {total_added['socks4']}, SOCKS5 {total_added['socks5']}")
        print(f"   📊 Overall: {total_processed} processed, {total_filtered} filtered out")
        
        # Show why we might have fewer proxies than expected
        if total_processed > 0:
            success_rate = ((total_processed - total_filtered) / total_processed) * 100
            print(f"   🎯 Success rate: {success_rate:.1f}%")
            
            if success_rate < 50:
                print("   ⚠️  Low success rate - many proxies may be invalid/duplicate")
                print("   💡 Consider checking the API response format or adding filters")

    # ----------------------------- public API ------------------------------
    def collect(self) -> None:
        print("🚀 Starting proxy collection...")
        
        # Set a maximum time limit for the entire collection process
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Collection process timed out after {COLLECTION_TIMEOUT//60} minutes")
        
        # Set timeout for Unix-like systems (Windows will use a different approach)
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(COLLECTION_TIMEOUT)  # Use configurable timeout
        except (AttributeError, OSError):
            # Windows doesn't support SIGALRM, we'll use a different approach
            pass

        try:
            # HTML-based SOCKS4 table
            print("📡 Scraping SOCKS4 from socks-proxy.net ...")
            socks4 = self._scrape_socksnet()
            self.proxy_dict["socks4"].update(socks4)
            print(f"   ✅ +{len(socks4)}")

            # checkerproxy archive
            print("📚 Pulling checkerproxy.net archive (10 days) ...")
            self._scrape_checkerproxy_archive()
            print("   ✅ Archive merged into HTTP/SOCKS5 buckets")

            # Bulk plaintext & HTML sources
            self._collect_text_sources()

            # JSON rotators (getproxylist.com) - can be skipped if problematic
            self._collect_json_rotators()

            # GeoNode paginated JSON list
            self._collect_geonode_free()

            print("\n🎉 Collection complete!")
            for p in ("http", "socks4", "socks5"):
                print(f"   {p.upper():6}: {len(self.proxy_dict[p])}")
            print(f"   Total : {sum(len(v) for v in self.proxy_dict.values())}")
            
        except TimeoutError:
            print("\n⏰ Collection process timed out after 30 minutes")
            print("Partial results will be saved...")
        except KeyboardInterrupt:
            print("\n⏹️ Collection interrupted by user")
            print("Partial results will be saved...")
        except Exception as e:
            print(f"\n❌ Collection failed with error: {e}")
            print("Partial results will be saved...")
        finally:
            # Clear timeout
            try:
                signal.alarm(0)
            except (AttributeError, OSError):
                pass

    def save(self) -> None:
        print("\n💾 Saving proxy files...")
        import os
        out_dir = Path('.')
        print(f"   📂 Working directory: {os.getcwd()}")

        # Get timestamp once for all files
        now = dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        for proto, proxies in self.proxy_dict.items():
            path = out_dir / f"{proto}.txt"
            print(f"   📝 Writing {proto}.txt ({len(proxies)}) ... ", end="")
            with path.open('w', encoding="utf-8") as f:
                f.write(f"# Updated: {now}\n")  # Force file change
                f.write(f"# Total: {len(proxies)} proxies\n\n")
                for p in sorted(proxies):
                    f.write(p + "\n")
            print(f"✅ (saved to {path.resolve()})")

        # Consolidated CSV
        csv_path = out_dir / "ProxyList.csv"
        now = dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        counts = {p: len(self.proxy_dict[p]) for p in ("http", "socks4", "socks5")}
        with csv_path.open('w', newline='', encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["HTTP Proxies", "Socks4 Proxies", "Socks5 Proxies",
                             "HTTP Count", "Socks4 Count", "Socks5 Count", "Timestamp"]) 
            writer.writerow(["", "", "", counts["http"], counts["socks4"], counts["socks5"], now])

            max_len = max(counts.values()) if counts else 0
            http_list = sorted(self.proxy_dict["http"]) 
            socks4_list = sorted(self.proxy_dict["socks4"]) 
            socks5_list = sorted(self.proxy_dict["socks5"]) 

            for i in range(max_len):
                row = [
                    http_list[i] if i < len(http_list) else "",
                    socks4_list[i] if i < len(socks4_list) else "",
                    socks5_list[i] if i < len(socks5_list) else "",
                    "", "", ""
                ]
                writer.writerow(row)

        print(f"✅ Saved combined sheet to {csv_path.resolve()}")
        print(f"🎯 Total proxies: {sum(counts.values())}  •  Timestamp: {now}")


if __name__ == '__main__':
    downloader = DownloadProxies()
    downloader.collect()
    downloader.save()
