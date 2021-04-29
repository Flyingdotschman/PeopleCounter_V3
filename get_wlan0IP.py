import os
import json


def get_wlan0ip():
    routes = json.loads(os.popen("ip -j -4 route").read())

    for r in routes:
        if r.get("dev") == "wlan0" and r.get("prefsrc"):
            ip = r['prefsrc']
            continue
    print(f"IP: {ip}")
    print(ip)
    return ip

