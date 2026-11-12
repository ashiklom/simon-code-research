"""Station networks. Each module exposes NETWORK, VARS {name: (kind, units, attrs)},
stations() -> DataFrame and fetch_site(row, years) -> hourly DataFrame (UTC, end-of-hour)."""

NETWORKS = {"USCRN": "uscrn", "SURFRAD": "surfrad", "SCAN": "nrcs", "SNOTEL": "nrcs", "ISUSM": "iem",
            "NEON": "neon", "AMERIFLUX": "ameriflux"}
