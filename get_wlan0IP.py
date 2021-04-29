import socket
import os
import json
gw = os.popen("ip -4 route show default").read().split()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect((gw[2], 0))
ipaddr = s.getsockname()[0]
gateway = gw[2]
host = socket.gethostname()
print("IP:", ipaddr, " GW:", gateway, " Host:", host)



routes = json.loads(os.popen("ip -j -4 route")).read()

for r in routes:
    if r.get("dev") == "wlan0" and r.get("prefsrc"):
        ip = r['prefsrc']
        continue
print(f"IP: {ip}")
