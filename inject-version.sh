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
if [ -n "$VERCEL_GIT_COMMIT_SHA" ]; then
    if [ -n "$VERCEL_BUILD_CREATED_AT" ] && [[ "$VERCEL_BUILD_CREATED_AT" =~ ^[0-9]+$ ]]; then
        if [ ${#VERCEL_BUILD_CREATED_AT} -ge 13 ]; then
            BUILD_EPOCH=$((VERCEL_BUILD_CREATED_AT / 1000))
        else
            BUILD_EPOCH=$VERCEL_BUILD_CREATED_AT
        fi

        if date -d "@$BUILD_EPOCH" +'%Y-%m-%d %I:%M %p MST' >/dev/null 2>&1; then
            COMMIT_TIMESTAMP=$(TZ='America/Denver' date -d "@$BUILD_EPOCH" +'%Y-%m-%d %I:%M %p MST')
        else
            COMMIT_TIMESTAMP=$(TZ='America/Denver' date -r "$BUILD_EPOCH" +'%Y-%m-%d %I:%M %p MST')
        fi
    else
        # On Vercel without a timestamp env var, use build time in Mountain Time
        COMMIT_TIMESTAMP=$(TZ='America/Denver' date +'%Y-%m-%d %I:%M %p MST')
    fi
else
    # Local: get actual commit timestamp
    COMMIT_TIMESTAMP=$(TZ='America/Denver' git log -1 --format='%cd' --date=format:'%Y-%m-%d %I:%M %p MST' 2>/dev/null || date +'%Y-%m-%d %I:%M %p MST')
fi

# Create version string
VERSION="$COMMIT_HASH • $COMMIT_TIMESTAMP"

# Replace placeholder with version info in index.html
sed -i.bak "s|__BUILD_VERSION__|$VERSION|g" index.html

echo "✅ Injected version: $VERSION"
