"""Non-blocking status LED patterns for device lifecycle (MicroPython)."""

try:
    from machine import Pin
    import time

    _HAS_PIN = True
except ImportError:
    Pin = None
    time = None
    _HAS_PIN = False

# Lifecycle states
BOOT = "boot"
WIFI_CONNECTING = "wifi_connecting"
WIFI_OK = "wifi_ok"
MQTT_CONNECTING = "mqtt_connecting"
RUNNING = "running"
FAULT = "fault"
ERROR = "error"

# (on_ms, off_ms) blink segments per state — keep ON phases >= 200ms so they're visible
_PATTERNS = {
    BOOT: [(200, 200), (200, 200), (200, 400)],
    WIFI_CONNECTING: [(300, 700)],
    WIFI_OK: [(150, 150), (150, 500)],
    MQTT_CONNECTING: [(300, 300)],
    RUNNING: [(250, 1750)],
    FAULT: [(150, 150)],
    ERROR: [(900, 300)],
}


class StatusLed:
    """Drive one LED with state-based blink patterns (non-blocking)."""

    def __init__(self, pin=21, active_low=True, enabled=True):
        self.pin_num = pin
        self.active_low = active_low
        self.enabled = enabled and _HAS_PIN
        self._pin = None
        self._state = BOOT
        self._segment = 0
        self._on = False
        self._phase_start = 0
        self._last_tick = 0
        self._init_error = None
        if self.enabled:
            try:
                self._pin = Pin(pin, Pin.OUT)
                self._off()
            except Exception as e:
                self.enabled = False
                self._pin = None
                self._init_error = str(e)
        if time:
            self._phase_start = time.ticks_ms()
            self._last_tick = self._phase_start

    def set_state(self, state):
        if state == self._state:
            return
        self._state = state
        self._segment = 0
        self._on = False
        if time:
            self._phase_start = time.ticks_ms()
        self._apply(False)

    @property
    def state(self):
        return self._state

    def _apply(self, on):
        self._on = on
        if not self.enabled or not self._pin:
            return
        if self.active_low:
            self._pin.value(0 if on else 1)
        else:
            self._pin.value(1 if on else 0)

    def _off(self):
        self._apply(False)

    def tick(self):
        """Advance blink pattern; call often from the main loop."""
        if not self.enabled or not time:
            return
        now = time.ticks_ms()
        self._last_tick = now
        pattern = _PATTERNS.get(self._state, _PATTERNS[RUNNING])
        on_ms, off_ms = pattern[self._segment % len(pattern)]
        duration = on_ms if self._on else off_ms
        if time.ticks_diff(now, self._phase_start) < duration:
            return
        self._phase_start = now
        if self._on:
            self._apply(False)
        else:
            self._apply(True)
            self._segment += 1

    def self_test(self, blinks=5):
        """Blocking visibility test at boot — flashes the orange user LED."""
        if not _HAS_PIN:
            print("LED self_test: no machine.Pin (not on device?)")
            return False
        try:
            pin = Pin(self.pin_num, Pin.OUT)
            for _ in range(blinks):
                pin.value(0 if self.active_low else 1)
                time.sleep(0.25)
                pin.value(1 if self.active_low else 0)
                time.sleep(0.25)
            self._pin = pin
            self.enabled = True
            self._off()
            print("LED self_test: OK on GPIO", self.pin_num)
            return True
        except Exception as e:
            print("LED self_test: FAIL —", e)
            self.enabled = False
            self._init_error = str(e)
            return False


def hardware_test(pin=21, active_low=True, blinks=5):
    """Run directly from REPL: import led; led.hardware_test()"""
    return StatusLed(pin=pin, active_low=active_low).self_test(blinks=blinks)


def create_from_secrets(secrets_mod=None):
    """Build StatusLed using optional secrets.LED_PIN / LED_ACTIVE_LOW / LED_ENABLED."""
    pin = 21
    active_low = True
    enabled = True
    if secrets_mod:
        pin = getattr(secrets_mod, "LED_PIN", pin)
        active_low = getattr(secrets_mod, "LED_ACTIVE_LOW", active_low)
        enabled = getattr(secrets_mod, "LED_ENABLED", enabled)
    status = StatusLed(pin=pin, active_low=active_low, enabled=enabled)
    if not status.enabled:
        msg = status._init_error or "disabled or unavailable"
        print("LED init:", msg, "(pin=%s)" % pin)
    return status
