#!/bin/bash

# Configuration
BROKER="hivemq.cloud"
PORT=8883
USER="username"
PASS="password"
TOPIC="test/test"
COUNT=20  # Number of packets to send

# Send N packets with sequential IDs
for i in $(seq 1 $COUNT); do
  PAYLOAD="message-$i"
  mosquitto_pub --host "$BROKER" --port "$PORT" \
    -u "$USER" -P "$PASS" \
    -t "$TOPIC" -m "$PAYLOAD" -q 0 &
done

# Optional: wait for all background jobs to finish
wait
echo "✅ Sent $COUNT messages to $TOPIC"