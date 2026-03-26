import threading
import time

TWEPOCH = 1770000000000
WORKER_ID_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1
SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1


class SnowflakeGenerator:
    def __init__(self, worker_id: int) -> None:
        if worker_id < 0 or worker_id > MAX_WORKER_ID:
            raise ValueError(f"worker_id must be in [0, {MAX_WORKER_ID}]")
        self.worker_id = worker_id
        self.sequence = 0
        self.last_timestamp = -1
        self._lock = threading.Lock()

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._timestamp()
        return timestamp

    def next_id(self) -> int:
        with self._lock:
            timestamp = self._timestamp()
            if timestamp < self.last_timestamp:
                raise RuntimeError("clock moved backwards")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & SEQUENCE_MASK
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp
            return (
                ((timestamp - TWEPOCH) << (WORKER_ID_BITS + SEQUENCE_BITS))
                | (self.worker_id << SEQUENCE_BITS)
                | self.sequence
            )
