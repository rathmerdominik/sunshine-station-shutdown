import sys
import time
import tomli
import psutil
import uvicorn
import asyncio
import logging
import datetime
import threading
import subprocess
import pyamdgpuinfo


from fastapi import FastAPI, status, HTTPException, WebSocket, WebSocketDisconnect

from systemd import journal
from systemd.journal import APPEND

from wakeonlan import send_magic_packet

config = {}
with open("config.toml", "rb") as file:
    config = tomli.load(file)

app = FastAPI()

clients = 0
start_time = 0
shutdown_time = float(config["TIME_TO_SHUTDOWN"])
uvicorn_process = None


def shutdown():
    logging.info("Shutting down system!")
    subprocess.run("systemctl", "shutdown")


def countdown_shutdown_thread():
    global clients
    global start_time

    j = journal.Reader()
    j.add_match(_SYSTEMD_USER_UNIT="sunshine.service")
    j.seek_tail()

    start_time = time.time()
    th = threading.Timer(600.0, shutdown)
    th.start()

    logging.info("Timer started ")
    while True:
        for entry in j:
            if "CLIENT CONNECTED" in entry["MESSAGE"]:
                clients += 1
                logging.info(f"Client connected. Remaining clients: {clients}")
                th.cancel()
                start_time = 0
                logging.info("Client connected. Timer stopped.")
            if (
                "CLIENT DISCONNECTED" in entry["MESSAGE"]
                or "Process terminated" in entry["MESSAGE"]
            ):
                if clients > 0:
                    clients -= 1
                logging.info(f"Client disconnected. Remaining clients: {clients}")

                if clients == 0:
                    start_time = time.time()
                    th = threading.Timer(shutdown_time, shutdown)
                    th.start()
                    logging.info("No Clients connected. Timer restarted.")


@app.websocket("/shutdown-get-remaining-time")
async def get_remaining_time(websocket: WebSocket):
    await websocket.send_text(str(shutdown_time - (time.time() - start_time)))


@app.get("/shutdown-get-connected-clients")
async def get_connected_clients():
    logging.info("Returning connected clients.")
    return {"connected_clients": str(clients)}


@app.post("/reboot")
async def reboot():
    logging.info("Reboot requested!")
    subprocess.run("systemctl", "reboot")


@app.get("/disk-usage")
async def get_disk_usage():
    logging.info("Returning current disk usage.")
    return {"usage": str(psutil.disk_usage("/"))}


@app.get("/cpu-cores")
async def get_cpu_info():
    logging.info("Returning current cpu information.")
    return {"cores": str(psutil.cpu_count())}


@app.websocket("/get-sunshine-log")
async def get_sunshine_log(websocket: WebSocket):
	await websocket.accept()
	while True:
		j = journal.Reader()
		j.add_match(_SYSTEMD_USER_UNIT="sunshine.service")
		j.seek_realtime(j.seek_realtime(datetime.datetime.now() - datetime.timedelta(minutes=20)))

		for entry in j:
			await websocket.send_text(entry["MESSAGE"])

@app.websocket("/gpu-info/{info}")
async def gpu_info_ws(websocket: WebSocket, info: str):
    await websocket.accept()
    if pyamdgpuinfo.detect_gpus() == 0:
        await websocket.close(
            1011, "No AMD GPU found. The program currently only supports AMD GPUs!"
        )

    gpu: pyamdgpuinfo.GPUInfo = pyamdgpuinfo.get_gpu(0)

    while True:
        try:
            if info == "load":
                await websocket.send_text(str(gpu.query_load() * 100))
            elif info == "vram":
                await websocket.send_text(str(gpu.query_vram_usage()))
            elif info == "temp":
                await websocket.send_text(str(gpu.query_temperature()))
            elif info == "volt":
                await websocket.send_text(str(gpu.query_graphics_voltage()))
            elif info == "watt":
                await websocket.send_text(str(gpu.query_power()))

        except RuntimeError:
            continue
        except Exception as e:
            await websocket.close(1011, str(e))


@app.websocket("/cpu-info/{info}")
async def cpu_info_ws(websocket: WebSocket, info: str):
    await websocket.accept()

    while True:
        try:
            if info == "cores":
                await websocket.send_text(str(psutil.cpu_count()))
            elif info == "freq":
                await websocket.send_text(str(psutil.cpu_freq))
            elif info == "usage":
                await websocket.send_text(str(psutil.cpu_percent()))
            elif info == "load-avg":
                await websocket.send_text(str(psutil.getloadavg()))
        except Exception as e:
            await websocket.close(1011, str(e))


@app.websocket("/ram-info/{info}")
async def ram_info_ws(websocket: WebSocket, info: str):
    await websocket.accept()

    while True:
        try:
            if info == "swap":
                await websocket.send_text(str(psutil.swap_memory()))
            elif info == "memory":
                await websocket.send_text(str(psutil.virtual_memory()))
        except Exception as e:
            await websocket.close(1011, str(e))


if __name__ == "__main__":
    try:
        logging.basicConfig(
            level=config["LOG_LEVEL"],
            format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%d/%b/%Y %H:%M:%S",
            stream=sys.stdout,
        )
        if float(config["TIME_TO_SHUTDOWN"]) > 0:
            thread = threading.Thread(target=countdown_shutdown_thread)
            thread.start()
            
        # This threading here has to be done because uvicorn is too stupid to properly shutdown on SIGINT
        uvicorn_thread = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={
                "host": config["IP_ADDRESS"],
                "port": config["PORT"],
            }
        )
        uvicorn_process = uvicorn_thread._target
    except KeyboardInterrupt:
        if uvicorn_process:
            uvicorn_process.kill()
        sys.exit(0)
