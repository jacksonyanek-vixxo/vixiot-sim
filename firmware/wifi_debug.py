"""WiFi connection debugger — run on ESP32 via REPL or: mpremote run wifi_debug.py"""

import network
import time

try:
    import secrets
except ImportError:
    secrets = None

STAT_NAMES = {
    1000: "IDLE",
    1001: "CONNECTING",
    1010: "GOT_IP",
    201: "NO_AP_FOUND",
    202: "WRONG_PASSWORD",
    203: "BEACON_TIMEOUT",
    204: "HANDSHAKE_TIMEOUT",
    -1: "CONNECT_FAIL",
    -2: "NO_AP",
    -3: "WRONG_PASSWORD_LEGACY",
}


def stat_name(code):
    return STAT_NAMES.get(code, "UNKNOWN(%s)" % code)


def reset_sta(wlan):
    print("\n--- reset STA ---")
    try:
        wlan.active(False)
        time.sleep(1)
    except Exception as e:
        print("  active(False) error:", e)
    wlan.active(True)
    time.sleep(1)
    print("  active:", wlan.active())
    print("  status:", stat_name(wlan.status()))


def scan_networks(wlan):
    print("\n--- scan ---")
    nets = wlan.scan()
    print("  found:", len(nets))
    target = getattr(secrets, "WIFI_SSID", None) if secrets else None
    target_seen = False
    for ssid_b, bssid, channel, rssi, authmode, hidden in nets:
        ssid = ssid_b.decode("utf-8", "replace")
        mark = " <-- target" if target and ssid == target else ""
        if target and ssid == target:
            target_seen = True
        print("  %r ch=%s rssi=%s auth=%s hidden=%s%s" % (ssid, channel, rssi, authmode, hidden, mark))
    if target and not target_seen:
        print("  WARNING: target SSID %r not in scan results" % target)
    return nets


def poll_connect(wlan, timeout_s=30):
    print("\n--- connect poll (%ss) ---" % timeout_s)
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        s = wlan.status()
        c = wlan.isconnected()
        if s != last:
            print("  status=%s (%s) connected=%s" % (s, stat_name(s), c))
            last = s
        if c:
            return True
        time.sleep(0.5)
    print("  TIMEOUT")
    return False


def test_mqtt_reach(broker, port=1883):
    print("\n--- MQTT TCP probe %s:%s ---" % (broker, port))
    try:
        import socket
        addr = socket.getaddrinfo(broker, port)[0][-1]
        print("  resolved:", addr)
        s = socket.socket()
        s.settimeout(5)
        s.connect(addr)
        s.close()
        print("  TCP connect: OK")
        return True
    except Exception as e:
        print("  TCP connect: FAIL —", e)
        return False


def main():
    print("=" * 40)
    print("WiFi debug")
    print("=" * 40)

    if secrets is None:
        print("ERROR: secrets.py not found on device")
        return

    ssid = getattr(secrets, "WIFI_SSID", None)
    password = getattr(secrets, "WIFI_PASSWORD", None)
    broker = getattr(secrets, "MQTT_BROKER", None)
    print("SSID:", repr(ssid))
    print("password set:", bool(password))
    print("MQTT_BROKER:", broker)

    wlan = network.WLAN(network.STA_IF)
    print("\n--- initial ---")
    print("  active:", wlan.active())
    print("  connected:", wlan.isconnected())
    print("  status:", stat_name(wlan.status()))
    try:
        print("  MAC:", wlan.config("mac"))
    except Exception as e:
        print("  MAC error:", e)

    reset_sta(wlan)
    scan_networks(wlan)

    if wlan.isconnected():
        print("\n--- already connected ---")
        print("  ifconfig:", wlan.ifconfig())
    else:
        print("\n--- connect ---")
        print("  calling wlan.connect(...)")
        try:
            wlan.connect(ssid, password)
        except Exception as e:
            print("  connect() raised:", e)
            return

        if poll_connect(wlan, 30):
            print("\n--- success ---")
            print("  ifconfig:", wlan.ifconfig())
            if broker:
                test_mqtt_reach(broker, getattr(secrets, "MQTT_PORT", 1883))
        else:
            print("\n--- failed ---")
            print("  final status:", stat_name(wlan.status()))
            print("  hints:")
            s = wlan.status()
            if s == 201:
                print("    - SSID not visible: 2.4GHz? closer to AP? typo in secrets?")
            elif s in (202, -3):
                print("    - Wrong password")
            elif s in (203, 204):
                print("    - Weak signal or AP dropped connection")
            elif s == 1000:
                print("    - Never left IDLE; try reset_sta() again or replug board")

    print("\n" + "=" * 40)


main()
