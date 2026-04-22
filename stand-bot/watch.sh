#!/bin/bash
# Check if a .py file is provided as an argument
if [ $# -eq 0 ] || [[ ! $1 =~ \.py$ ]]; then
    echo "Error: Please provide a .py file as an argument."
    echo "Usage: $0 <filename.py>"
    exit 1
fi

# Extract the filename without extension
filename=$(basename "$1" .py)

# Watch for changes in the .py file and rebuild using nodemon
nodemon --watch "$1" stripboard.py --ext py --exec "./build.sh $filename"
