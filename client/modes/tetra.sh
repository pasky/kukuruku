#!/bin/bash

dir=`dirname "$0"`

tmpdir=`mktemp -d`
pipe="$tmpdir/fifo"
mkfifo "$pipe"

cat - | "$dir"/tetra.py "$@" -p "$pipe" &

tpid=$!

function ex() {
  kill $tpid
  rm $pipe
  rmdir $tmpdir
}

trap ex SIGINT SIGTERM

mkdir -p /tmp/tetra-dumpdir

xterm -e "tetra-rx -d /tmp/tetra-dumpdir $pipe"

ex
