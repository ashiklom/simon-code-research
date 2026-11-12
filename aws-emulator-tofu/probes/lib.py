"""Helpers for probe checks (run on the host with the emulator env loaded)."""
import base64
import io
import json
import os
import time
import zipfile

import boto3
import requests

CA = os.environ.get("AWS_CA_BUNDLE")
ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
if CA:
    os.environ["REQUESTS_CA_BUNDLE"] = CA


def client(name):
    return boto3.client(name)


def session():
    s = requests.Session()
    s.verify = CA
    return s


def invoke(fn, payload=None):
    """Invoke a Lambda; return (function_error, parsed_payload)."""
    from botocore.config import Config
    r = boto3.client("lambda", config=Config(retries={"max_attempts": 1}, read_timeout=60)).invoke(FunctionName=fn, Payload=json.dumps(payload or {}).encode())
    raw = r["Payload"].read()
    try:
        body = json.loads(raw)
    except ValueError:
        body = raw.decode(errors="replace")
    return r.get("FunctionError"), body


def wait_for(pred, timeout=60, every=2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(every)
    return None


def logs_contain(group, needle, timeout=60):
    def find():
        try:
            ev = client("logs").filter_log_events(logGroupName=group)["events"]
        except Exception:  # noqa: BLE001
            return None
        return [e["message"] for e in ev if needle in e["message"]] or None
    return wait_for(find, timeout)


def result(status, detail, **extra):
    """status: works | partial | gap"""
    return {"status": status, "detail": detail, **extra}


def b64url(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()
