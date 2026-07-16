#!/usr/bin/env python3
"""Headless CLI wrapper for the shared MQTT sink hub."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sink.hub import SinkHub

Sink = SinkHub


def main():
    parser = argparse.ArgumentParser(description="VixIoT MQTT sink subscriber")
    parser.add_argument("--broker", default=os.getenv("VIXIOT_BROKER", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("VIXIOT_MQTT_PORT", "1883")))
    parser.add_argument("--tls", action="store_true", help="Use TLS (e.g. HiveMQ Cloud port 8883)")
    parser.add_argument("--user", default=os.getenv("VIXIOT_MQTT_USER"), help="MQTT username")
    parser.add_argument("--password", default=os.getenv("VIXIOT_MQTT_PASSWORD"), help="MQTT password")
    parser.add_argument("--device", default=None, help="Filter to one device_id")
    args = parser.parse_args()
    SinkHub(args.broker, args.port, args.device, args.user, args.password, args.tls).run()


if __name__ == "__main__":
    main()
