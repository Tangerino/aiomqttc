mosquitto_sub \
  --host 15880ce84c254f03abe400915e786926.s1.eu.hivemq.cloud \
  --port 8883 \
  -u mp_demo -P Abigpwd1 \
  -t micropython/stats -q 1 |
while read -r line; do
  date
  echo "$line" | jq -r '
    to_entries[] |
    .key as $section |
    .value | to_entries | sort_by(.key)[] |
    "\($section) | \(.key) | \(.value)"
  ' | column -t -s '|'
  echo
done