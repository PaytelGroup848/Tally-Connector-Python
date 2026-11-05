import threading
import time
from shared.tally_lock import get_tally_lock

def test_tally_lock_queue_sequential_execution():
    """
    Verifies that multiple concurrent threads attempting to send XML to Tally Prime
    are strictly queued sequentially via TALLY_LOCK, preventing concurrent flooding
    and Stack Overflow crashes (c00000fd).
    """
    lock = get_tally_lock()
    active_in_critical_section = 0
    max_concurrent_seen = 0
    execution_order = []
    thread_count = 5

    def worker_task(thread_id: int):
        nonlocal active_in_critical_section, max_concurrent_seen
        with lock:
            active_in_critical_section += 1
            if active_in_critical_section > max_concurrent_seen:
                max_concurrent_seen = active_in_critical_section
            time.sleep(0.02)  # Simulate XML request duration to Tally
            execution_order.append(thread_id)
            active_in_critical_section -= 1

    threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Guaranteed that at no point did more than 1 thread enter critical section
    assert max_concurrent_seen == 1
    assert len(execution_order) == thread_count

