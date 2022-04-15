#!/bin/bash

dir=`dirname "$0"`

tmpdir=`mktemp -d`
pipe="$tmpdir/fifo"
mkfifo "$pipe"

cat - | "$dir"/sonde_sgp.py "$@" -p "$pipe" &

tpid=$!

function ex() {
  kill $tpid
  rm $pipe
  rmdir $tmpdir
}

trap ex SIGINT SIGTERM

urxvt -e rs41ecc -vv $pipe

exit
