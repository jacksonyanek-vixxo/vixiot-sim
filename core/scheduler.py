"""Sample vs publish interval scheduler."""


class Scheduler:
    """Tracks when to sample and when to publish."""

    def __init__(self, sample_interval_ms=1000, publish_interval_s=30):
        self.sample_interval_ms = sample_interval_ms
        self.publish_interval_s = publish_interval_s
        self._sample_accum_ms = 0
        self._publish_accum_s = 0

    def update_intervals(self, sample_interval_ms=None, publish_interval_s=None):
        if sample_interval_ms is not None:
            self.sample_interval_ms = max(100, int(sample_interval_ms))
        if publish_interval_s is not None:
            self.publish_interval_s = max(1, int(publish_interval_s))

    def tick(self, elapsed_ms):
        """Advance clocks; return (should_sample, should_publish)."""
        self._sample_accum_ms += elapsed_ms
        self._publish_accum_s += elapsed_ms / 1000.0

        should_sample = False
        while self._sample_accum_ms >= self.sample_interval_ms:
            self._sample_accum_ms -= self.sample_interval_ms
            should_sample = True

        should_publish = False
        if self._publish_accum_s >= self.publish_interval_s:
            self._publish_accum_s = 0
            should_publish = True

        return should_sample, should_publish

    def force_publish_ready(self):
        self._publish_accum_s = self.publish_interval_s
