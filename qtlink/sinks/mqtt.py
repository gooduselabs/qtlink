"""MQTT publish sink (paho-mqtt). QoS 1 by default; success only after the broker acknowledges."""
from __future__ import annotations
import os
import ssl

from .files import password


def publish(dest: dict, local_path: str):
    import paho.mqtt.client as mqtt
    with open(local_path, "rb") as f:
        payload = f.read()
    topic = dest.get("topic") or "qtlink/{station}/data"
    topic = topic.format(station=dest.get("_station", "station"), file=os.path.basename(local_path))
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=dest.get("client_id", ""))
    if dest.get("username"):
        c.username_pw_set(dest["username"], password(dest) or None)
    if dest.get("tls"):
        c.tls_set(ca_certs=dest.get("ca_file"), cert_reqs=ssl.CERT_REQUIRED)
    timeout = float(dest.get("timeout", 15))
    rc = c.connect(dest.get("host", "localhost"), int(dest.get("port", 8883 if dest.get("tls") else 1883)),
                   keepalive=int(timeout) + 30)
    if rc != 0:
        raise ConnectionError(f"MQTT connect failed rc={rc}")
    c.loop_start()
    try:
        info = c.publish(topic, payload, qos=int(dest.get("qos", 1)), retain=bool(dest.get("retain", False)))
        info.wait_for_publish(timeout)
        if not info.is_published():
            raise TimeoutError(f"MQTT publish to {topic} not acknowledged within {timeout:g}s")
    finally:
        c.disconnect()
        c.loop_stop()
