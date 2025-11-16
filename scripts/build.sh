#!/bin/bash
set -e

# Remove old builds
rm -f dist/*

# Build fresh package
uv build


