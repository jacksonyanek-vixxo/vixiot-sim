"""WiFi platform adapter (MicroPython network / CPython stub)."""

try:
    import network
    _HAS_NETWORK = True
except ImportError:
    _HAS_NETWORK = False


def connect(ssid, password, timeout_s=30):
    if not _HAS_NETWORK:
        return True
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
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
