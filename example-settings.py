# List of the Meter IDs to watch
# List may contain only one entry - [12345678]
# or multiple entries - [12345678, 98765432, 12340123]
METERS_FILTER = []
BYPASS_METER_FILTER = True

# If no authentication, leave MQTT_USER and MQTT_PASSWORD empty
MQTT_HOST = ''
MQTT_PORT = 1883
MQTT_CLIENT_ID = "metermon"
MQTT_USER = ''
MQTT_PASSWORD = ''
MQTT_TOPIC_PREFIX = "metermon"

RTL_TCP_SERVER = "127.0.0.1:1234"

RTLAMR_MSGTYPE = "all"  # see RTLAMR_MSGTYPE note below
RTLAMR_UNIQUE = "true"

METERMON_SEND_RAW = "False"
METERMON_SEND_BY_ID = "True"
METERMON_ELECTRIC_DIVISOR = 1000.0
METERMON_GAS_DIVISOR = 1.0
METERMON_WATER_DIVISOR = 10.0

# rtlamr tuning. Decode only the protocols your meters use: each extra
# protocol costs CPU (on a Pi 3, "all" saturates a core and drops samples).
# e.g. "scm+" or "scm,scm+,r900"
# RTLAMR_MSGTYPE = "scm+"
# Lower symbol length = lower sample rate = less CPU (rtlamr default 72)
RTLAMR_SYMBOLLENGTH = 32

# Home Assistant MQTT discovery: auto-create one sensor per meter plus a
# "Last reading" timestamp sensor. Requires METERMON_SEND_BY_ID = "True".
METERMON_HA_DISCOVERY = "False"
METERMON_HA_DISCOVERY_PREFIX = "homeassistant"
# "False" = only announce the "Last reading" sensor, not one sensor per meter
METERMON_HA_DISCOVERY_METERS = "True"

# Retained heartbeat on <prefix>/heartbeat every N seconds, with the time of
# the last published reading, so you can alert when readings stop.
METERMON_HEARTBEAT_SECS = 60

# Watchdogs: exit (systemd restarts us) if MQTT is down this long; restart
# rtlamr if it prints nothing for this long.
METERMON_MQTT_DOWN_EXIT_SECS = 300
METERMON_RTLAMR_STALL_SECS = 1800
