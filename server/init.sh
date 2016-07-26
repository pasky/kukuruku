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

./server -s 2048000 -p "$ppm" -f "$freq" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -s "$2" -w 1024 &
spid=$!

echo "Server PID $spid, use 'gdb ./server $spid -ex c' to debug"

trap "kill $spid" SIGINT SIGTERM

./osmosdr-input.py -d "$1" -r "$2" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -p "$ppm"
kill $spid
