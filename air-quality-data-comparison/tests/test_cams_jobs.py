import pandas as pd

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
