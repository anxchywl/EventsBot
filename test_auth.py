import requests
import time
import subprocess
import sys

proc = subprocess.Popen([".venv/bin/uvicorn", "app.web.main:web_app", "--port", "8002"])
time.sleep(2)
try:
    resp = requests.post("http://127.0.0.1:8002/api/auth/session", data="{}")
    print("Status:", resp.status_code)
    print("Content:", resp.text)
except Exception as e:
    print(e)
finally:
    proc.terminate()
