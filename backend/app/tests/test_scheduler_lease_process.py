import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.paths import RUN_DIR
from app.main import app
from app.scheduler.lease import SchedulerLease

HOLD_LEASE = """
import sys
import time
from pathlib import Path
from app.scheduler.lease import SchedulerLease

lease = SchedulerLease(Path(sys.argv[1]))
print(lease.acquire(), flush=True)
time.sleep(float(sys.argv[2]))
lease.release()
"""


def _start_holder(path: Path, seconds: float = 8.0) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", HOLD_LEASE, str(path), str(seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    line = process.stdout.readline().strip()
    assert line == "True", f"lease holder failed to start: {line}"
    return process


def test_second_process_cannot_acquire_until_holder_exits(tmp_path):
    path = tmp_path / "run" / "scheduler.lock"
    holder = _start_holder(path, 20)
    try:
        contender = SchedulerLease(path)
        assert contender.acquire() is False
        holder.terminate()
        holder.wait(timeout=10)
        deadline = time.time() + 5
        acquired = False
        while time.time() < deadline:
            if contender.acquire():
                acquired = True
                break
            time.sleep(0.1)
        assert acquired, "the lease was not released when the holder exited"
        contender.release()
    finally:
        if holder.poll() is None:
            holder.kill()


def test_standby_instance_reports_its_role_and_does_not_own_the_scheduler():
    path = RUN_DIR / "scheduler.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = _start_holder(path, 20)
    try:
        with TestClient(app) as standby_client:
            response = standby_client.get("/api/health")
            assert response.status_code == 200
            assert response.json()["data"]["schedulerRole"] == "standby"
    finally:
        holder.terminate()
        holder.wait(timeout=10)
