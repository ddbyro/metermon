#!/usr/local/bin/python3.13
import json
import select
import subprocess
import socket
import sys
import time
import paho.mqtt.client as mqtt
from python_settings import settings
from typing import Optional

# read in needed env variables
MQTT_BROKER_HOST = settings.MQTT_HOST
MQTT_BROKER_PORT = settings.MQTT_PORT
MQTT_CLIENT_ID = settings.MQTT_CLIENT_ID
MQTT_USERNAME = settings.MQTT_USER
MQTT_PASSWORD = settings.MQTT_PASSWORD
MQTT_TOPIC_PREFIX = settings.MQTT_TOPIC_PREFIX
RTL_TCP_SERVER = settings.RTL_TCP_SERVER
RTLAMR_MSGTYPE = settings.RTLAMR_MSGTYPE
RTLAMR_UNIQUE = settings.RTLAMR_UNIQUE
METERMON_SEND_RAW = settings.METERMON_SEND_RAW
METERMON_SEND_BY_ID = settings.METERMON_SEND_BY_ID
METERMON_ELECTRIC_DIVISOR = settings.METERMON_ELECTRIC_DIVISOR
#METERMON_GAS_DIVISOR = settings.METERMON_GAS_DIVISOR
METERMON_WATER_DIVISOR = settings.METERMON_WATER_DIVISOR
METERS_FILTER = settings.METERS_FILTER
BYPASS_METER_FILTER = settings.BYPASS_METER_FILTER


R900_LOOKUP = {
    "HISTORY": {
        0: "0",
        1: "1-2",
        2: "3-7",
        3: "8-14",
        4: "15-21",
        5: "22-34",
        6: "35+",
    },
    "INTENSITY": {
        0: "None",
        1: "Low",
        2: "High",
    }
}
R900_ATTRIBS = {
    "Leak": "HISTORY",
    "NoUse": "HISTORY",
    "BackFlow": "INTENSITY",
    "LeakNow": "INTENSITY",
}

# Helper to parse host:port
_def_host = "127.0.0.1"
_def_port = 1234

def _parse_host_port(hostport: str):
    try:
        host, port_str = hostport.rsplit(":", 1)
        return host.strip() or _def_host, int(port_str)
    except Exception:
        return hostport or _def_host, _def_port

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties=None):
    # print connection statement
    try:
        conn_str = mqtt.connack_string(reason_code)
    except Exception:
        conn_str = str(reason_code)
    print(f"Connected to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} with result code {reason_code}: {conn_str}")

    # set mqtt status message
    client.publish(MQTT_TOPIC_PREFIX+"/status", payload="Online", qos=1, retain=True)

def on_disconnect(client, userdata, *args):
    # paho v2 calls (client, userdata, flags, reason_code, properties); v1 calls
    # (client, userdata, rc). The old 4-arg signature raised TypeError on v2,
    # which killed paho's network thread for good on the first disconnect.
    reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
    print(f"Disconnected from broker (RC={reason_code}). paho will reconnect...")

# Watchdog thresholds (override in settings.py if desired)
MQTT_DOWN_EXIT_SECS = getattr(settings, "METERMON_MQTT_DOWN_EXIT_SECS", 300)
RTLAMR_STALL_SECS = getattr(settings, "METERMON_RTLAMR_STALL_SECS", 1800)
_mqtt_down_since: Optional[float] = None


def _check_mqtt_alive():
    """Exit (so systemd restarts us) if the broker link has been down too long."""
    global _mqtt_down_since
    if client.is_connected():
        _mqtt_down_since = None
        return
    now = time.monotonic()
    if _mqtt_down_since is None:
        _mqtt_down_since = now
    elif now - _mqtt_down_since > MQTT_DOWN_EXIT_SECS:
        print(f"MQTT disconnected for >{MQTT_DOWN_EXIT_SECS}s; exiting so systemd restarts metermon.")
        sys.exit(1)

# set up mqtt client (use callback API v2 to avoid deprecation warning)
if hasattr(mqtt, "CallbackAPIVersion"):
    client = mqtt.Client(
        client_id=MQTT_CLIENT_ID,
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
else:
    # Older paho-mqtt that doesn't support callback_api_version
    client = mqtt.Client(
        client_id=MQTT_CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
if MQTT_USERNAME and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    print("Username and password set.")
client.will_set(MQTT_TOPIC_PREFIX+"/status", payload="Offline", qos=1, retain=True)  # set LWT
client.on_connect = on_connect  # on connect callback
client.on_disconnect = on_disconnect  # on disconnect callback
# never let a callback exception kill the network thread
client.suppress_exceptions = True
# exponential reconnect delay for broker
if hasattr(client, "reconnect_delay_set"):
    client.reconnect_delay_set(min_delay=1, max_delay=120)

# connect to broker
client.connect(MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
client.loop_start()

# start RTLAMR with resilience
cmdargs = [
    'rtlamr',
    '-format=json',
    f'-server={RTL_TCP_SERVER}',
    f'-msgtype={RTLAMR_MSGTYPE}',
    f'-unique={RTLAMR_UNIQUE}',
    # Lower symbol length = lower sample rate = far less CPU. rtlamr's default
    # (72 -> 2.36 MS/s) saturates a Pi 3 core and drops samples; 32 -> ~1 MS/s.
    f'-symbollength={getattr(settings, "RTLAMR_SYMBOLLENGTH", 32)}',
]

RTL_HOST, RTL_PORT = _parse_host_port(RTL_TCP_SERVER)


def _wait_for_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _publish_status(state: str, detail: Optional[dict] = None):
    try:
        payload = {"rtlamr": state}
        if detail:
            payload.update(detail)
        client.publish(MQTT_TOPIC_PREFIX+"/rtlamr_status", json.dumps(payload), retain=True)
    except Exception:
        pass

def _handle_message(data):
    msg = json.loads('{"Protocol":"Unknown","Type":"Unknown","ID":"Unknown","Consumption":0,"Unit":"Unknown"}')

    # read data, create json objects, and publish MQTT message for every meter message received

    # set Protocol
    msg['Protocol'] = data['Type']

    # SCM messages
    if msg['Protocol'] == "SCM":
        msg['ID'] = str(data['Message']['ID'])
        if data['Message']['Type'] in (4, 5, 7, 8):  # electric meter
            msg['Type'] = "Electric"
            msg['Consumption'] = data['Message']['Consumption'] * 10 / METERMON_ELECTRIC_DIVISOR  # convert to kWh
            msg['Unit'] = "kWh"
        elif data['Message']['Type'] in (2, 9, 12):  # gas meter
            msg['Type'] = "Gas"
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = "ft³"
        elif data['Message']['Type'] in (3, 11, 13):  # water meter
            msg['Type'] = "Water"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR  # convert to gal
            msg['Unit'] = "gal"
    # SCM+ messages
    elif msg['Protocol'] == "SCM+":
        msg['ID'] = str(data['Message']['EndpointID'])
        if data['Message']['EndpointType'] in (4, 5, 7, 8):  # electric meter
            msg['Type'] = "Electric"
            msg['Consumption'] = data['Message']['Consumption'] * 10 / METERMON_ELECTRIC_DIVISOR  # convert to kWh
            msg['Unit'] = "kWh"
        elif data['Message']['EndpointType'] in (2, 9, 12, 156, 188, 220):  # gas meter
            msg['Type'] = "Gas"
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = "ft³"
        elif data['Message']['EndpointType'] in (3, 11, 13, 171):  # water meter
            msg['Type'] = "Water"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR  # convert to gal
            msg['Unit'] = "gal"
    # IDM messages
    elif msg['Protocol'] == "IDM":
        msg['Type'] = "Electric"
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionCount'] * 10 / METERMON_ELECTRIC_DIVISOR  # convert to kWh
        msg['Unit'] = "kWh"
    # NetIDM messages
    elif msg['Protocol'] == "NetIDM":
        msg['Type'] = "Electric"
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionNet'] * 10 / METERMON_ELECTRIC_DIVISOR  # convert to kWh
        msg['Unit'] = "kWh"
    # R900 messages
    elif msg['Protocol'] == "R900":
        msg['Type'] = "Water"
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR  # convert to gal
        msg['Unit'] = "gal"
        for attr, kind in R900_ATTRIBS.items():
            value = data['Message'].get(attr)
            if value is not None:
                try:
                    msg[attr] = R900_LOOKUP[kind][value]
                except KeyError:
                    print(f"Could not process R900 value ({attr}: {value})")

    # R900bcd messages
    elif msg['Protocol'] == "R900BCD":
        msg['Type'] = "Water"
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR  # convert to gal
        msg['Unit'] = "gal"
    # filter meter ID
    if BYPASS_METER_FILTER or msg['ID'] in METERS_FILTER:
        # filter out cases where consumption value is negative
        if msg['Consumption'] > 0:
            client.publish(MQTT_TOPIC_PREFIX+"/output", json.dumps(msg), retain=True)  # publish
            if METERMON_SEND_BY_ID.lower() == "true":
                client.publish(MQTT_TOPIC_PREFIX+"/"+msg['ID'], json.dumps(msg), retain=True)  # also publish by ID if enabled
            print(json.dumps(msg))  # also print
        # send raw json message if enabled
        if METERMON_SEND_RAW.lower() == "true":
            client.publish(MQTT_TOPIC_PREFIX+"/raw", json.dumps(data), retain=True)  # publish


backoff = 2
max_backoff = 60

while True:
    if not _wait_for_tcp(RTL_HOST, RTL_PORT, timeout=3.0):
        msg = f"rtl_tcp server {RTL_HOST}:{RTL_PORT} not reachable. Will retry in {backoff}s."
        print(msg)
        _publish_status("rtl_tcp_unreachable", {"host": RTL_HOST, "port": RTL_PORT, "retry_in": backoff})
        time.sleep(backoff)
        backoff = min(max_backoff, backoff * 2)
        continue

    # TCP reachable; (re)start rtlamr
    print(f"Starting rtlamr with server {RTL_HOST}:{RTL_PORT}...")
    _publish_status("starting", {"host": RTL_HOST, "port": RTL_PORT})
    try:
        proc = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print("rtlamr executable not found. Ensure it is installed and in PATH.")
        _publish_status("rtlamr_missing")
        time.sleep(backoff)
        backoff = min(max_backoff, backoff * 2)
        continue

    # Reset backoff on successful start
    backoff = 2
    _publish_status("running")

    # read output of RTLAMR
    last_output = time.monotonic()
    try:
        while True:
            if proc.stdout is None:
                break
            # wake up every 30s even with no output so the watchdogs can run
            ready, _, _ = select.select([proc.stdout], [], [], 30)
            _check_mqtt_alive()
            if not ready:
                if proc.poll() is not None:
                    break
                if time.monotonic() - last_output > RTLAMR_STALL_SECS:
                    print(f"No rtlamr output for {RTLAMR_STALL_SECS}s; restarting rtlamr.")
                    _publish_status("stalled")
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            last_output = time.monotonic()
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # Pass through non-JSON lines from rtlamr (errors/logs)
                try:
                    print(line.decode(errors='ignore').rstrip())
                except Exception:
                    print(str(line))
                continue
            try:
                _handle_message(data)
            except Exception as e:
                print(f"Skipping message that failed to parse ({type(e).__name__}: {e}): {line[:200]!r}")
    finally:
        # Process ended or stalled; make sure rtlamr is gone before restarting
        if proc.poll() is None:
            proc.terminate()
        try:
            rc = proc.wait(timeout=5)
        except Exception:
            proc.kill()
            rc = None
        print(f"rtlamr exited (rc={rc}). Restarting in {backoff}s...")
        _publish_status("stopped", {"rc": rc, "retry_in": backoff})
        time.sleep(backoff)
        backoff = min(max_backoff, backoff * 2)
