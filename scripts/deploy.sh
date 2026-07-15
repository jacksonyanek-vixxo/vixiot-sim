#!/usr/bin/env bash
# Deploy vixiot-sim firmware to ESP32-S3 over USB (MicroPython + mpremote).
#
# Usage:
#   ./scripts/deploy.sh                     # auto-detect port
#   ./scripts/deploy.sh /dev/cu.usbmodem1101
#
# If you see "could not enter raw repl":
#   1. Close Thonny / any serial monitor
#   2. Unplug USB, plug back in, run this script within ~5s
#   3. Or erase flash and reflash MicroPython (see README hardware section)
#
# Prerequisites:
#   pip install mpremote
#   cp firmware/secrets.example.py secrets.py  # edit WiFi/MQTT first

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${1:-}"
if [[ -z "$PORT" ]]; then
  PORT="$(mpremote connect list | awk '/usbmodem|ttyACM|ttyUSB/ {print $1; exit}')"
fi

if [[ -z "$PORT" ]]; then
  echo "No serial port found. Pass one explicitly: ./scripts/deploy.sh /dev/cu.usbmodem1101" >&2
  exit 1
fi

if [[ ! -f secrets.py ]]; then
  echo "Missing secrets.py — copy and edit firmware/secrets.example.py first." >&2
  exit 1
fi

MRP=(mpremote connect "${PORT}")

interrupt_device() {
  python3 - "$PORT" <<'PY'
import sys
import time
try:
    import serial
except ImportError:
    sys.exit(0)
port = sys.argv[1]
try:
    ser = serial.Serial(port, 115200, timeout=0.5)
    for _ in range(3):
        ser.write(b"\x03")  # Ctrl+C
        time.sleep(0.15)
    ser.write(b"\x04")  # Ctrl+D soft reset
    time.sleep(1.5)
    ser.close()
except Exception:
    pass
PY
}

mp_cp() {
  local src="$1"
  local dst="$2"
  local attempt
  for attempt in 1 2 3; do
    if "${MRP[@]}" cp "$src" "$dst"; then
      return 0
    fi
    echo "  retry ${attempt}/3: ${src} (interrupt + soft-reset) ..."
    interrupt_device
    sleep 1
  done
  echo "Failed to copy ${src}. Close other serial apps, replug USB, run again quickly." >&2
  return 1
}

echo "Deploying to ${PORT} ..."
interrupt_device

# main.py is copied LAST — if it starts with missing core/, the board crash-loops
# and mpremote can no longer enter raw REPL.
mp_cp firmware/boot.py :boot.py
mp_cp firmware/config.json :config.json
mp_cp secrets.py :secrets.py

"${MRP[@]}" exec "import os
try:
    os.mkdir('core')
except OSError:
    pass" > /dev/null

mp_cp core/__init__.py ':core/__init__.py'
mp_cp core/aggregation.py ':core/aggregation.py'
mp_cp core/buffer.py ':core/buffer.py'
mp_cp core/config.py ':core/config.py'
mp_cp core/rng.py ':core/rng.py'
mp_cp core/espresso.py ':core/espresso.py'
mp_cp core/irregularities.py ':core/irregularities.py'
mp_cp core/runtime.py ':core/runtime.py'
mp_cp core/scheduler.py ':core/scheduler.py'
mp_cp core/schema.py ':core/schema.py'

mp_cp firmware/platform/clock.py :clock.py
mp_cp firmware/platform/mqtt.py :mqtt.py
mp_cp firmware/platform/storage.py :storage.py
mp_cp firmware/platform/wifi.py :wifi.py
mp_cp firmware/platform/led.py :led.py

echo "Copying main.py last ..."
mp_cp firmware/main.py :main.py

echo "Marking deploy complete (disables boot delay) ..."
"${MRP[@]}" exec "open('.deployed','w').close()"

echo "Resetting device ..."
"${MRP[@]}" reset

echo "Done."
