"""climate-product-compare: gridded weather/climate products vs station observations."""

try:  # silence Icechunk's per-open warnings about local-filesystem commit safety (one writer per repo here)
    import icechunk

    icechunk.set_logs_filter("error")
except Exception:  # pragma: no cover
    pass
