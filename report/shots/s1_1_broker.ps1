# Section 1.1 screenshot: the MQTT broker is running and listening.
"EMQX container:"
docker ps --filter "name=emqx" --format "table {{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
""
"Port 1883 (MQTT):"
netstat -ano | findstr ":1883"
""
"Port 18083 (dashboard):"
netstat -ano | findstr ":18083"
