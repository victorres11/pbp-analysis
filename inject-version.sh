#!/bin/bash
# Inject git commit hash and timestamp into index.html
# Uses Vercel env vars when available, falls back to local git

set -e

# Get commit hash (Vercel env var or local git)
if [ -n "$VERCEL_GIT_COMMIT_SHA" ]; then
    COMMIT_HASH="${VERCEL_GIT_COMMIT_SHA:0:7}"
else
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
fi

# Get commit timestamp
# Vercel doesn't provide timestamp env var, so we'll use current time on Vercel
if [ -n "$VERCEL_GIT_COMMIT_SHA" ]; then
    # On Vercel, use build time in Mountain Time
    COMMIT_TIMESTAMP=$(TZ='America/Denver' date +'%Y-%m-%d %I:%M %p MST')
else
    # Local: get actual commit timestamp
    COMMIT_TIMESTAMP=$(TZ='America/Denver' git log -1 --format='%cd' --date=format:'%Y-%m-%d %I:%M %p MST' 2>/dev/null || date +'%Y-%m-%d %I:%M %p MST')
fi

# Create version string
VERSION="$COMMIT_HASH • $COMMIT_TIMESTAMP"

# Replace v2.0 with version info in index.html
sed -i.bak "s|<span class=\"text-xs text-zinc-500 ml-1\">v2.0</span>|<span class=\"text-xs text-zinc-500 ml-1\">$VERSION</span>|g" index.html

echo "✅ Injected version: $VERSION"
