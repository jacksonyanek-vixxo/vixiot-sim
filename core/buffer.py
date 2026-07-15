"""Store-and-forward buffer with ordered replay."""


class StoreForwardBuffer:
    """FIFO buffer for telemetry records during connectivity outages."""

    def __init__(self, max_size=500):
        self.max_size = max_size
        self._records = []

    def __len__(self):
        return len(self._records)

    def enqueue(self, record):
        self._records.append(record)
        while len(self._records) > self.max_size:
            self._records.pop(0)

    def replay_all(self):
        """Return all buffered records in FIFO order and clear buffer."""
        records = list(self._records)
        self._records = []
        return records

    def peek(self):
        return list(self._records)

    def clear(self):
        self._records = []

    def load_records(self, records):
        if records:
            self._records = list(records)[-self.max_size :]

    def dump_records(self):
        return list(self._records)
