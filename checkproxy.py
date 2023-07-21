import requests
import threading
import os 
import time
def test(type):
    if type in ['http','https']:
        with open("http.txt","r") as f:
            data=f.read().split("\n")
    else:
        with open("{}.txt".format(type),"r") as f:
            data=f.read().split("\n")
    print('> {} {} proxies will be check'.format(len(data),type))
    
    try:
        os.system('rm {}_checked.txt'.format(type))
    except:
        pass
    
    def process(i):
        try:
            requests.get("https://icanhazip.com/",proxies={"https":f"{type}://{i}"},timeout=30,)
        except:
            pass
        else:
            with open("{}_checked.txt".format(type),"a+") as f:
                f.write(i+"\n")

    for i in data:
        threading.Thread(target=process,args=(i,)).start()

    while threading.active_count() >1:
        time.sleep(1)
    
if __name__ == '__main__':
    test('socks4')
    test('socks5')
    test('http')
    test('https')
    