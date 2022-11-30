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

RTLAMR_MSGTYPE = "all"
RTLAMR_UNIQUE = "true"

METERMON_SEND_RAW = "False"
METERMON_SEND_BY_ID = "True"
METERMON_ELECTRIC_DIVISOR = 1000.0
METERMON_GAS_DIVISOR = 1.0
METERMON_WATER_DIVISOR = 10.0
