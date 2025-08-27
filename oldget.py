import json
import datetime
import requests
import re
import csv
from datetime import datetime as dt
from pathlib import Path

class DownloadProxies:
    """
    Scrape free proxy lists, dedupe by protocol, write .txt files and
    a consolidated CSV (TestProxySheet.csv) with a timestamp, counts,
    and three columns: HTTP, SOCKS4, SOCKS5.
    """
    def __init__(self) -> None:
        self.api = {
            'socks4': [
                "https://api.proxyscrape.com/?request=displayproxies&proxytype=socks4&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=socks4",
                 "https://api.openproxylist.xyz/socks4.txt",
                 "https://proxyspace.pro/socks4.txt",
                 "https://sunny9577.github.io/proxy-scraper/generated/socks4_proxies.txt",
                 'https://openproxy.space/list/socks4',
                 'https://cdn.rei.my.id/proxy/SOCKS4',
                 "https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/socks4.txt",
                 "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
                 "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
                 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt',
                 'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt',
                 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt',
                 'https://raw.githubusercontent.com/Noctiro/getproxy/master/file/socks4.txt',
                 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks4.txt',
                 'https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/socks4.txt',
                 'https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks4.txt',
                 'https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt',
                 'https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt',
                 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt',
                 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt'
            ],
            'socks5': [
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=socks5",
                 "https://api.openproxylist.xyz/socks5.txt",
                 'https://openproxy.space/list/socks5',
                 'https://spys.me/socks.txt',
                 'https://proxyspace.pro/socks5.txt',
                 "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
                 'https://cdn.rei.my.id/proxy/SOCKS5',
                 "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
                 "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
                 "https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/socks5.txt",
                 "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
                 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt',
                 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks5_proxies.txt',
                 'https://raw.githubusercontent.com/Noctiro/getproxy/master/file/socks5.txt',
                 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt',
                 'https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/socks5.txt',
                 'https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks5.txt',
                 'https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt',
                 'https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt',
                 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt',
                 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt'
            ],
            'http': [
                "https://api.proxyscrape.com/?request=displayproxies&proxytype=http&timeout=10000&country=all&simplified=true",
                "https://www.proxy-list.download/api/v1/get?type=http",
                 "https://www.proxy-list.download/api/v1/get?type=https",
                 "https://spys.me/proxy.txt",
                 "https://api.openproxylist.xyz/http.txt",
                 'https://openproxy.space/list/http',
                 'https://proxyspace.pro/http.txt',
                 'https://proxyspace.pro/https.txt',
                 "https://sunny9577.github.io/proxy-scraper/generated/http_proxies.txt",
                 'https://cdn.rei.my.id/proxy/HTTP',
                 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt',
                 "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
                 'https://github.com/monosans/proxy-list/raw/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/mzyui/proxy-list/refs/heads/main/http.txt',
                 'https://github.com/mmpx12/proxy-list/raw/master/http.txt',
                 'https://github.com/mmpx12/proxy-list/raw/master/https.txt',
                 'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt',
                 'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt',
                 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt',
                 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/https_proxies.txt',
                 'https://raw.githubusercontent.com/Noctiro/getproxy/master/file/http.txt',
                 'https://raw.githubusercontent.com/Noctiro/getproxy/master/file/https.txt',
                 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt',
                 'https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/ArrayIterator/proxy-lists/main/proxies/https.txt',
                 'https://raw.githubusercontent.com/zenjahid/FreeProxy4u/master/http.txt',
                 'https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/https.txt',
                 'https://raw.githubusercontent.com/tuanminpay/live-proxy/master/http.txt',
                 'https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt',
                 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt',
                 'https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt',
                 'https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt',
                 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt',
                 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt',
                 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt',
                 'https://raw.githubusercontent.com/aslisk/proxyhttps/main/https.txt',
                 'https://raw.githubusercontent.com/saisuiu/uiu/main/free.txt',
                 'https://raw.githubusercontent.com/berkay-digital/Proxy-Scraper/main/proxies.txt',
                 'https://raw.githubusercontent.com/MrMarble/proxy-list/main/all.txt'
            ]
        }
        self.proxy_dict = { 'socks4': set(), 'socks5': set(), 'http': set() }

    @staticmethod
    def _scrape_socksnet() -> list[str]:
        """Extract SOCKS4 proxies from https://www.socks-proxy.net/"""
        try:
            html = requests.get("https://www.socks-proxy.net/", timeout=5).text
            tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
            if not tbody:
                return []
            rows = re.findall(r"<tr><td>(.*?)</td><td>(\\d+)</td>", tbody.group(1))
            return [f"{ip}:{port}" for ip, port in rows]
        except:
            return []

    def _scrape_checkerproxy_archive(self) -> None:
        """Append proxies from checkerproxy.net archive for last 10 days."""
        today = datetime.date.today()
        for offset in range(10):
            day = today - datetime.timedelta(days=offset)
            url = f"https://api.checkerproxy.net/v1/landing/archive/{day:%Y-%m-%d}"
            try:
                resp = requests.get(url, timeout=5)
                data = resp.json().get("data", {}).get("proxyList", [])
                targets = data if isinstance(data, list) else list(data.values())
                for proxy in targets:
                    self.proxy_dict["socks5"].add(proxy)
                    self.proxy_dict["http"].add(proxy)
            except:
                continue

    def collect(self) -> None:
        """Fetch and dedupe proxies from all sources."""
        # HTML-based SOCKS4
        self.proxy_dict["socks4"].update(self._scrape_socksnet())
        # Archive-based extra
        self._scrape_checkerproxy_archive()
        # API-based lists
        for proto, urls in self.api.items():
            for url in urls:
                try:
                    text = requests.get(url, timeout=5).text
                    found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}", text)
                    self.proxy_dict[proto].update(found)
                except:
                    continue

    def save(self) -> None:
        """Write per-protocol .txt and consolidated CSV sheet."""
        out_dir = Path('.')
        # Write individual .txt files
        for proto, proxies in self.proxy_dict.items():
            path = out_dir / f"{proto}.txt"
            with path.open('w') as f:
                for p in sorted(proxies):
                    f.write(p + "\n")
            print(f"> Saved {len(proxies)} {proto} proxies to {path}")

        # Write TestProxySheet.csv
        csv_path = out_dir / "ProxyList.csv"
        now = dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        counts = {p: len(self.proxy_dict[p]) for p in ("http", "socks4", "socks5")}
        with csv_path.open('w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            # Write header row with column names and metadata
            writer.writerow([
                "HTTP Proxies", "Socks4 Proxies", "Socks5 Proxies",
                "HTTP Count", "Socks4 Count", "Socks5 Count", "Timestamp"
            ])
            # Write metadata row with counts and timestamp
            writer.writerow([
                "", "", "",
                counts["http"], counts["socks4"], counts["socks5"], now
            ])
            
            # Write data rows
            max_len = max(counts.values())
            http_list = sorted(self.proxy_dict["http"])
            socks4_list = sorted(self.proxy_dict["socks4"])
            socks5_list = sorted(self.proxy_dict["socks5"])
            
            for i in range(max_len):
                row = [
                    http_list[i] if i < len(http_list) else "",
                    socks4_list[i] if i < len(socks4_list) else "",
                    socks5_list[i] if i < len(socks5_list) else "",
                    "", "", ""  # Empty columns for counts and timestamp in data rows
                ]
                writer.writerow(row)
        print(f"> Saved combined sheet to {csv_path}")

if __name__ == '__main__':
    downloader = DownloadProxies()
    downloader.collect()
    downloader.save()