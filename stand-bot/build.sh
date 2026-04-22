#!/bin/bash
uv run python $1.py
open $1.pdf
osascript -e 'activate application "Cursor"'
