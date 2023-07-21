import os
import sys
import threading

from systemd import journal
from systemd.journal import APPEND


def shutdown():
    os.system("systemctl poweroff")


def main():
    
    clients = 0
    j = journal.Reader()
    j.add_match(_SYSTEMD_USER_UNIT="sunshine.service")
    j.seek_tail()

    th = threading.Timer(600.0, shutdown)
    th.start()
    print("Timer started!", file=sys.stderr)
    while True:
        response = j.wait()
        if response == APPEND:
            for entry in j:
                if "CLIENT CONNECTED" in entry["MESSAGE"]:
                    clients += 1
                    print(f"Client connected: {clients}", file=sys.stderr)
                    th.cancel()
                    print("Timer reset", file=sys.stderr)
                if "CLIENT DISCONNECTED" in entry["MESSAGE"] or "Process terminated" in entry["MESSAGE"]:
                    clients -= 1
                    print(f"Client connected: {clients}", file=sys.stderr)

                    if clients == 0:
                        th = threading.Timer(600.0, shutdown)
                        th.start()
                        print("Timer restarted", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
