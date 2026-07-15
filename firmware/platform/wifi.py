"""WiFi platform adapter (MicroPython network / CPython stub)."""

try:
    import network
    _HAS_NETWORK = True
except ImportError:
    _HAS_NETWORK = False


def _reset_interface(wlan):
    """ESP32 requires STA reset before scan/connect (see micropython#10900)."""
    try:
        wlan.active(False)
        import time
        time.sleep(0.5)
    except Exception:
        pass
    wlan.active(True)
    try:
        import time
        time.sleep(0.5)
    except Exception:
        pass


def scan(timeout_s=10):
    if not _HAS_NETWORK:
        return []
    wlan = network.WLAN(network.STA_IF)
    _reset_interface(wlan)
    return wlan.scan()


def connect(ssid, password, timeout_s=30):
    if not _HAS_NETWORK:
        return True
    wlan = network.WLAN(network.STA_IF)
    _reset_interface(wlan)
    if wlan.isconnected():
        return True
    wlan.connect(ssid, password)
    for _ in range(timeout_s * 2):
        if wlan.isconnected():
            return True
        try:
            import time
            time.sleep(0.5)
        except Exception:
            pass
    return wlan.isconnected()


def is_connected():
    if not _HAS_NETWORK:
        return True
    wlan = network.WLAN(network.STA_IF)
    return wlan.isconnected()
