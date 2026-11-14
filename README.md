# metermon

Reads utility meters (electric, gas, water) with an RTL-SDR dongle via
[rtlamr](https://github.com/bemasher/rtlamr) and publishes readings to MQTT.
Optionally announces sensors to Home Assistant with MQTT discovery.

## Install (Raspberry Pi / Debian)

```bash
sudo apt install rtl-sdr
# rtlamr: install a release binary to /usr/local/bin/rtlamr
sudo git clone https://github.com/ddbyro/metermon.git /opt/metermon
sudo chown -R ddbyro:ddbyro /opt/metermon
pip install -r /opt/metermon/requirements.txt
cp /opt/metermon/example-settings.py /opt/metermon/settings.py   # then edit
sudo cp /opt/metermon/deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rtl_tcp metermon
```

Adjust `User=`, the Python path in `ExecStart=`, and the rtl_tcp address in
the unit files to match your host.

## MQTT topics (prefix `metermon`)

| Topic | Content |
|---|---|
| `metermon/status` | `Online` / `Offline` (LWT), retained |
| `metermon/<meter id>` | latest reading JSON for that meter, retained |
| `metermon/output` | latest reading from any meter, retained |
| `metermon/heartbeat` | `{ts, last_reading, readings_published, uptime_s}`, retained |
| `metermon/rtlamr_status` | rtlamr state (`running`, `stalled`, ...), retained |

## Alerting when readings stop

With `METERMON_HA_DISCOVERY = "True"`, Home Assistant gets a
`sensor.metermon_last_reading` timestamp. Alert when it is older than a few
hours (see `hass_example.yaml`). Note that `RTLAMR_UNIQUE = "true"` only
publishes a meter when its value changes, so a meter with no usage stays quiet.
