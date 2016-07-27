#!/bin/bash

if [ $# -ne 3 ]; then
  echo "Usage: $0 device rate ppm"
  exit 2
fi

sdr="/tmp/sdrpipe"
tune="/tmp/tunepipe"
gain="30"
ppm="$3"
freq="$(( 100 * 1000 * 1000 ))"

[ ! -p "$sdr" ] && mkfifo "$sdr"
[ ! -p "$tune" ] && mkfifo "$tune"

# set -b :: for ipv4 and ipv6 all interfaces
./server -s 2048000 -p "$ppm" -f "$freq" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -a -s "$2" -b 127.0.0.1 -t 4444 -w 1024 &
spid=$!

echo "Server PID $spid, use 'gdb ./server $spid -ex c' to debug"

trap "kill $spid" SIGINT SIGTERM

./osmosdr-input.py -d "$1" -r "$2" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -p "$ppm"
kill $spid
