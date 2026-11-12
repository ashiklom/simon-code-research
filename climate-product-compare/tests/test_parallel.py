import os

from cpc.parallel import process_map


def _square_or_die(x):
    # simulate a worker killed by a hard deadline: dies the first time it sees 5
    flag = f"/tmp/cpc-test-die-{os.getppid()}-{x}"
    if x == 5 and not os.path.exists(flag):
        open(flag, "w").close()
        os._exit(17)
    return x * x


def test_process_map_recovers_from_dead_worker():
    assert list(process_map(_square_or_die, range(12), workers=3, timeout=30)) == [i * i for i in range(12)]
