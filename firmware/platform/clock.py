"""Clock adapter: NTP sync with monotonic ISO-8601 fallback."""

try:
    import time
except ImportError:
    time = None

try:
    import ntptime
    _HAS_NTP = True
except ImportError:
    _HAS_NTP = False

_epoch_offset = 0
_boot_monotonic = 0


def sync_ntp():
    global _epoch_offset, _boot_monotonic
    if time is None:
        return False
    _boot_monotonic = time.time()
    if _HAS_NTP:
        try:
            ntptime.settime()
            _epoch_offset = 0
            return True
        except Exception:
            pass
    _epoch_offset = 1700000000
    return False


def now_iso():
    if time is None:
        return "1970-01-01T00:00:00Z"
    ts = time.time() if _epoch_offset == 0 else _boot_monotonic + _epoch_offset
    try:
        tm = time.gmtime(ts)
        return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
            tm[0], tm[1], tm[2], tm[3], tm[4], tm[5],
        )
    except Exception:
        return "1970-01-01T00:00:00Z"


def sleep_ms(ms):
    if time:
        time.sleep_ms(ms) if hasattr(time, "sleep_ms") else time.sleep(ms / 1000.0)
