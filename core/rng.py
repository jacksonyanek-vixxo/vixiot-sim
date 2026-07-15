"""Portable deterministic RNG (CPython + MicroPython — no random.Random)."""


class SeededRng:
    """Small LCG; same seed yields same sequence on host and device."""

    def __init__(self, seed=0):
        self._state = int(seed) & 0xFFFFFFFF

    def random(self):
        self._state = (1103515245 * self._state + 12345) & 0x7FFFFFFF
        return self._state / 0x7FFFFFFF
