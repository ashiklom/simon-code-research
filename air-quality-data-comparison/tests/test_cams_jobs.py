import pandas as pd

from aqc.products import cams
from aqc.products.cams import pick_job, same_request

REQ = {"variable": ["ozone", "temperature"], "model_level": ["60"], "date": "2018-03-12/2018-06-12",
       "time": ["00:00", "03:00"], "data_format": "netcdf"}


def test_same_request_ignores_list_order():
    other = dict(REQ, variable=["temperature", "ozone"])
    assert same_request(REQ, other)
    assert not same_request(REQ, dict(REQ, date="2018-06-13/2018-09-13"))
    assert not same_request(REQ, {k: v for k, v in REQ.items() if k != "model_level"})


def test_pick_job_newest_usable_match():
    jobs = [
        {"jobID": "old", "processID": "ds", "status": "successful", "created": "2026-11-10T00:00:00"},
        {"jobID": "failed", "processID": "ds", "status": "failed", "created": "2026-11-19T02:00:00"},
        {"jobID": "other-ds", "processID": "x", "status": "accepted", "created": "2026-11-19T02:00:00"},
        {"jobID": "a", "processID": "ds", "status": "accepted", "created": "2026-11-19T01:00:00"},
        {"jobID": "b", "processID": "ds", "status": "successful", "created": "2026-11-19T01:30:00"},
    ]
    since = pd.Timestamp("2026-11-16")
    seen = []

    def req(jid):
        seen.append(jid)
        return jid in ("a", "old")

    assert pick_job(jobs, "ds", since, req) == "a"
    assert seen == ["b", "a"]  # newest first; wrong dataset/state/too old never fetched
    assert pick_job(jobs, "ds", since, lambda j: False) is None
    # finished jobs only (downloaded without taking the ADS slot): "a" is still queued
    assert pick_job(jobs, "ds", since, req, ("successful",)) is None
    assert pick_job(jobs, "ds", since, lambda j: j == "b", ("successful",)) == "b"


def test_forecast_blocks_are_clipped_calendar_months():
    import pandas as pd

    from aqc.products.cams import CAMSForecast

    keys = CAMSForecast().blocks(pd.Timestamp("2025-08-01 01:00"), pd.Timestamp("2025-10-15 00:00"))
    assert keys == [(pd.Timestamp("2025-08-01"), pd.Timestamp("2025-08-31")),
                    (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-09-30")),
                    (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-14"))]
    # resuming mid-month starts at the run date holding t0
    k = CAMSForecast().blocks(pd.Timestamp("2025-09-10 05:00"), pd.Timestamp("2025-09-20 00:00"))
    assert k == [(pd.Timestamp("2025-09-10"), pd.Timestamp("2025-09-19"))]


def test_ads_slot_serialises_threads(tmp_path, monkeypatch):
    import threading
    import time

    from aqc.products import cams

    monkeypatch.setattr(cams, "CACHE", tmp_path)
    inside, peak, lock = [0], [0], threading.Lock()

    def work():
        with cams._ads_slot():
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            time.sleep(0.05)
            with lock:
                inside[0] -= 1

    ts = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] == 1


class _Resp:
    def __init__(self, status, cr, body):
        self.status_code, self.headers, self.body = status, {"content-range": cr}, body

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield from (self.body[i : i + n] for i in range(0, len(self.body), n))


def test_fetch_ranges_rejects_ignored_range_and_short_reads(tmp_path, monkeypatch):
    data = bytes(range(256)) * 40  # 10,240 bytes
    calls = []

    def get(url, headers):
        a, b = map(int, headers["Range"][6:].split("-"))
        calls.append((a, b))
        if len(calls) == 2:  # server ignores Range: whole file, 200
            return _Resp(200, "", data)
        if len(calls) == 4:  # connection cut mid-part
            return _Resp(206, f"bytes {a}-{b}/{len(data)}", data[a : a + 100])
        return _Resp(206, f"bytes {a}-{b}/{len(data)}", data[a : b + 1])

    monkeypatch.setattr(cams.time, "sleep", lambda s: None)
    out = tmp_path / "x.download"
    cams.fetch_ranges("u", len(data), out, get=get, part=4096)
    assert out.read_bytes() == data
    assert calls == [(0, 4095), (4096, 8191), (4096, 8191), (8192, 10239), (8192, 10239)]
