#!/bin/bash

if [ $# -ne 4 ]; then
  echo "Usage: $0 device rate ppm listen-address"
  exit 2
fi

sdr="/tmp/sdrpipe"
tune="/tmp/tunepipe"
gain="30"
ppm="$3"
sample_rate="$2"
listen_address="$4"
freq="$(( 100 * 1000 * 1000 ))"

[ ! -p "$sdr" ] && mkfifo "$sdr"
[ ! -p "$tune" ] && mkfifo "$tune"

# set -b :: for ipv4 and ipv6 all interfaces
./server -p "$ppm" -f "$freq" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -a -s "$sample_rate" -b "$listen_address" -t 4444 -w 1024 &
spid=$!

echo "Server PID $spid, use 'gdb ./server $spid -ex c' to debug"

trap "kill $spid" SIGINT SIGTERM

./osmosdr-input.py -d "$1" -r "$2" -i "$tune" -o "$sdr" -f "$freq" -g "$gain" -p "$ppm"
kill $spid
