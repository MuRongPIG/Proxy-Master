import os
import platform
import threading
import time

def test(proxy_type):
    file_name = f"{proxy_type}.txt"
    if os.path.exists(file_name):
        with open(file_name, "r") as f:
            proxies = f.read().splitlines()
    else:
        print(f"No file named {file_name} found")
        return

    print(f'> {len(proxies)} {proxy_type} proxies will be checked')

    checked_file = f"{proxy_type}_checked.txt"
    if os.path.exists(checked_file):
        os.remove(checked_file)

    def ping_google(proxy):
        ip_port = proxy.split(':')
        if len(ip_port) != 2:
            return False
        ip, port = ip_port
        cmd = None

        if platform.system() == "Windows":
            cmd = f'ping -n 1 -w 1000 {ip}'
        else:
            cmd = f'ping -c 1 -W 1 {ip}'

        response = os.system(cmd)
        return response == 0

    def process(proxy):
        failure_count = 0
        for _ in range(2):  # Try twice
            if ping_google(proxy):
                with open(checked_file, "a") as f:
                    f.write(proxy + "\n")
                break
            else:
                failure_count += 1
            if failure_count >= 2:
                break

    threads = []
    for proxy in proxies:
        thread = threading.Thread(target=process, args=(proxy,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

if __name__ == '__main__':
    test('socks4')
    test('socks5')
    test('http')
    test('https')
