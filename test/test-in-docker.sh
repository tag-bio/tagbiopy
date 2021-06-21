#! /usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
docker build -t tagbior -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR/.."