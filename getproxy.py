import json
import time
import datetime
import requests
import re
class Downloadproxies():
    def __init__(self) -> None:
        self.api = {
    'socks4':[
        "https://api.proxyscrape.com/?request=displayproxies&proxytype=socks4&country=all",
        "https://www.proxy-list.download/api/v1/get?type=socks4",
        "https://www.proxyscan.io/download?type=socks4",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt',
        "https://api.openproxylist.xyz/socks4.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        "https://www.freeproxychecker.com/result/socks4_proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
        'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt',
        'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt',
        'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks4.txt',
        'https://raw.githubusercontent.com/RX4096/proxy-list/main/online/socks4.txt',
        'https://raw.githubusercontent.com/UptimerBot/proxy-list/main/proxies/socks4.txt',
        'https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/socks4.txt',
        'https://proxylist.live/nodes/socks4_1.php?page=1&showall=1',
        #'https://raw.githubusercontent.com/HyperBeats/proxy-list/main/socks4.txt',
        'https://openproxy.space/list/socks4'
        ],
    'socks5': [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all&simplified=true",
        "https://www.proxy-list.download/api/v1/get?type=socks5",
        "https://www.proxyscan.io/download?type=socks5",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        "https://api.openproxylist.xyz/socks5.txt",
        "https://www.freeproxychecker.com/result/socks5_proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
        'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
        'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt',
        'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks5.txt',
        'https://raw.githubusercontent.com/RX4096/proxy-list/main/online/socks5.txt',
        'https://raw.githubusercontent.com/manuGMG/proxy-365/main/SOCKS5.txt',
        'https://raw.githubusercontent.com/UptimerBot/proxy-list/main/proxies/socks5.txt',
        'https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/socks5.txt',
        #'https://raw.githubusercontent.com/HyperBeats/proxy-list/main/socks5.txt',
        'https://openproxy.space/list/socks5',
        'https://proxylist.live/nodes/socks5_1.php?page=1&showall=1',
        'https://spys.me/socks.txt'
        ],
    'http': [
        "https://api.proxyscrape.com/?request=displayproxies&proxytype=http",
        "https://www.proxy-list.download/api/v1/get?type=http",
        "https://www.proxyscan.io/download?type=http",
        "http://spys.me/proxy.txt",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "https://api.openproxylist.xyz/http.txt",
        "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",
        "http://alexa.lr2b.com/proxylist.txt",
        "http://rootjazz.com/proxies/proxies.txt",
        "https://www.freeproxychecker.com/result/http_proxies.txt",
        "http://proxysearcher.sourceforge.net/Proxy%20List.php?type=http",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
        "https://raw.githubusercontent.com/opsxcq/proxy-list/master/list.txt",
        "https://proxy-spider.com/api/proxies.example.txt",
        "https://multiproxy.org/txt_all/proxy.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/http.txt",
        "https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/https.txt",
        'https://raw.githubusercontent.com/UptimerBot/proxy-list/main/proxies/http.txt',
        'https://openproxy.space/list/http',
        'https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt',
        'https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list/data.txt',
        'https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt',
        'https://raw.githubusercontent.com/almroot/proxylist/master/list.txt',
        'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt',
        'https://raw.githubusercontent.com/aslisk/proxyhttps/main/https.txt',
        'https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/http.txt',
        'https://raw.githubusercontent.com/saisuiu/uiu/main/free.txt',
        'https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt',
        'https://proxylist.live/nodes/free_1.php?page=1&showall=1'
        #'https://raw.githubusercontent.com/HyperBeats/proxy-list/main/http.txt'
    ]}
        self.proxy_dict = {'socks4':[],'socks5':[],'http':[]}
        pass

    def get(self,type):
        for api in self.api[type]:
            self.proxy_list = []
            try:
                self.r = requests.get(api,timeout=5)
                if self.r.status_code == requests.codes.ok :
                    self.proxy_list += re.findall('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}',self.r.text)
                    self.proxy_dict[type] += list(set(self.proxy_list))
                    print('> Get {} {} ips from {}'.format(len(self.proxy_list),type,api))
            except:
                pass
        if type == 'socks4':
            try:
                r = requests.get("https://www.socks-proxy.net/",timeout=5)
                self.part = str(r.text)
                self.part = self.part.split("<tbody>")
                self.part = self.part[1].split("</tbody>")
                self.part = self.part[0].split("<tr><td>")
                self.proxies = ""
                for proxy in self.part:
                    proxy = proxy.split("</td><td>")
                    try:
                        if self.proxies != '':
                            self.proxies=self.proxies + proxy[0] + ":" + proxy[1] + "\n"
                    except:
                        pass
                if self.proxies != '':
                    self.proxy_list += self.proxies.split('\n')
                self.proxy_dict[type] += list(set(self.proxy_list))
            except:
                pass
        print('> Get {} proxies done'.format(type))

    def get_extra(self):
        for q in range(10):
            self.count = {'http':0,'socks5':0}
            self.day = datetime.date.today() + datetime.timedelta(-q)
            self.r = requests.get('https://checkerproxy.net/api/archive/{}-{}-{}'.format(self.day.year,self.day.month,self.day.day))
            if self.r.text != '[]': 
                self.json_result = json.loads(self.r.text)
                for i in self.json_result:
                    if i['ip'] == '172.23.0.1':
                        if i['type'] in [1,2] and i['addr'] in self.proxy_dict['http']:
                            self.proxy_dict['http'].remove(i['addr'])
                        if i['type'] == 4 and i['addr'] in self.proxy_dict['socks5']:
                            self.proxy_dict['socks5'].remove(i['addr'])
                    else:
                        if i['type'] in [1,2] :
                            self.count['http'] += 1
                            self.proxy_dict['http'].append(i['addr'])
                        if i['type'] == 4 :
                            self.count['socks5'] += 1
                            self.proxy_dict['socks5'].append(i['addr'])
                print('> Get {} http proxy ips from {}'.format(self.count['http'],self.r.url))
                print('> Get {} socks5 proxy ips from {}'.format(self.count['socks5'],self.r.url))
        
        self.proxy_dict['socks4'] = list(set(self.proxy_dict['socks4']))
        self.proxy_dict['socks5'] = list(set(self.proxy_dict['socks5']))
        self.proxy_dict['http'] = list(set(self.proxy_dict['http']))
        
        print('> Get extra proxies done')

    def get_all(self):
        self.get('socks4')
        self.get('socks5')
        self.get('http')
        self.get_extra()

    def save(self,type):
        self.proxy_dict[type] = list(set(self.proxy_dict[type]))
        self.out_file = '{}.txt'.format(type)
        f = open(self.out_file,'w')
        for i in self.proxy_dict[type]:
            if '#' in i or i == '\n':
                self.proxy_dict[type].remove(i)
            else:
                f.write(i + '\n')
        print("> Have already saved {} proxies list as ".format(len(self.proxy_dict[type])) + self.out_file)

    def save_all(self):
        self.save('socks4')
        self.save('socks5')
        self.save('http')

if __name__ == '__main__':
    d = Downloadproxies()
    d.get_all()
    d.save_all()