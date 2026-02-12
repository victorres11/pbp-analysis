#!/bin/bash
# Inject git commit hash and timestamp into index.html

set -e

# Get git commit hash (short)
COMMIT_HASH=$(git rev-parse --short HEAD)

# Get commit timestamp in Mountain Time
COMMIT_TIMESTAMP=$(TZ='America/Denver' git log -1 --format='%cd' --date=format:'%Y-%m-%d %I:%M %p MST')

# Create version string
VERSION="$COMMIT_HASH • $COMMIT_TIMESTAMP"

# Replace v2.0 with version info in index.html
sed -i.bak "s|<span class=\"text-xs text-zinc-500 ml-1\">v2.0</span>|<span class=\"text-xs text-zinc-500 ml-1\">$VERSION</span>|g" index.html

echo "✅ Injected version: $VERSION"
