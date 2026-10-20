from app.scheduler.lease import SchedulerLease


def test_scheduler_lease_can_be_released_and_reacquired(tmp_path):
    path = tmp_path / "run" / "scheduler.lock"
    first = SchedulerLease(path)
    assert first.acquire() is True
    first.release()

    second = SchedulerLease(path)
    assert second.acquire() is True
    second.release()
