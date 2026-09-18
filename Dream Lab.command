#!/bin/zsh
# Double-click this file in Finder to open the local math lab.
cd -- "${0:A:h}"
exec python3 -m dream_rsi lab --open
