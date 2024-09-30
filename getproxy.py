import json
import datetime
import requests
import re
class Downloadproxies():
    def __init__(self) -> None:
        self.api = {
    'socks4':[
        "https://api.proxyscrape.com/?request=displayproxies&proxytype=socks4&timeout=10000&country=all&simplified=true",
        "https://www.proxy-list.download/api/v1/get?type=socks4",
        "https://api.openproxylist.xyz/socks4.txt",
        'https://openproxy.space/list/socks4',
        'https://proxyspace.pro/socks4.txt',
        "https://sunny9577.github.io/proxy-scraper/generated/socks4_proxies.txt",
        'https://cdn.rei.my.id/proxy/SOCKS4',

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
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
        'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
        'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt',
        # 'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt',
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
        'https://www.proxy-list.download/api/v1/get?type=https'
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
        'https://raw.githubusercontent.com/MrMarble/proxy-list/main/all.txt',



    
    ]}
        self.proxy_dict = {'socks4':[],'socks5':[],'http':[]}
        pass

    def get_special1(self):
        proxy_list = []
        try:
            r = requests.get("https://www.socks-proxy.net/",timeout=5)
            part = str(r.text)
            part = part.split("<tbody>")
            part = part[1].split("</tbody>")
            part = part[0].split("<tr><td>")
            proxies = ""
            for proxy in part:
                proxy = proxy.split("</td><td>")
                try:
                    if proxies != '':
                        proxies = proxies + proxy[0] + ":" + proxy[1] + "\n"
                        if proxies != '':
                            proxy_list += proxies.split('\n')
                except:
                    pass
                
            return proxy_list
        except:
            return []

    def get_special2(self):
        for i in range(json.loads(requests.get('https://proxylist.geonode.com/api/proxy-summary').text)["summary"]['proxiesOnline'] // 100):
            proxies = json.loads(requests.get('https://proxylist.geonode.com/api/proxy-list?limit=100&page={}&sort_by=lastChecked&sort_type=desc'.format(i)).text)
            for p in proxies['data']:
                if p['protocols'][0] == 'https':
                    protocol = 'http'
                else:
                    protocol = p['protocols'][0]
                self.proxy_dict[protocol] .append('{}:{}'.format(p['ip'],p['port']))
        return

    def get(self):
        self.proxy_dict['socks4'] += self.get_special1()
        #self.get_special2()
        self.get_extra()
        
        for type in ['socks4','socks5','http']:
            for api in self.api[type]:
                self.proxy_list = []
                try:
                    self.r = requests.get(api,timeout=5)
                    if self.r.status_code == requests.codes.ok :
                        self.proxy_list += re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}",self.r.text)
                        self.proxy_dict[type] += list(set(self.proxy_list))
                        print('> Get {} {} ips from {}'.format(len(self.proxy_list),type,api))
                except:
                    pass

        print('> Get {} proxies done'.format(type))

    def get_extra(self):
        for q in range(20):
            self.count = {'http':0,'socks5':0}
            self.day = datetime.date.today() + datetime.timedelta(-q)
            self.r = requests.get('https://checkerproxy.net/api/archive/{}-{}-{}'.format(self.day.year,self.day.month,self.day.day))
            if self.r.text != '[]': 
                self.json_result = json.loads(self.r.text)
                for i in self.json_result:
                    if re.match(r"172\.*\.*\.*",i['ip']):
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

    def save(self):
        for type in ['socks4','socks5','http']:
            self.proxy_dict[type] = list(set(self.proxy_dict[type]))
            self.out_file = './{}.txt'.format(type)
            f = open(self.out_file,'w')
            for i in self.proxy_dict[type]:
                if '#' in i or i == '\n':
                    self.proxy_dict[type].remove(i)
                else:
                    f.write(i + '\n')
            print("> Have already saved {} proxies list as ".format(len(self.proxy_dict[type])) + self.out_file)

if __name__ == '__main__':
    d = Downloadproxies()
    d.get()
    d.save()
