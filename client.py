
import sys
import requests
import websockets
from websockets.sync.client import connect

response = requests.api.get("http://192.168.2.136:8000/shutdown-get-remaining-time")
print(response.status_code)
print(response.content)

response = requests.api.get("http://192.168.2.136:8000/shutdown-get-connected-clients")
print(response.status_code)
print(response.content)

response = requests.api.get("http://192.168.2.136:8000/kill")

with connect("ws://192.168.2.136:8000/get-sunshine-log") as websocket:
	while True:
		message = websocket.recv()
		print(f"Received: {message}")
		sys.stdout.flush()

