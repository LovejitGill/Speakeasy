#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LT_DIR="${SPEAKWELL_LT_DIR:-$PROJECT_DIR/.tools/LanguageTool-6.6}"
JAVA_DEFAULT="java"
if [[ -x "$PROJECT_DIR/.tools/java" ]]; then JAVA_DEFAULT="$PROJECT_DIR/.tools/java"; fi
JAVA_BIN="${SPEAKWELL_JAVA:-$JAVA_DEFAULT}"
cd "$LT_DIR"
# Without --public, LanguageTool listens locally. No browser CORS option.
exec "$JAVA_BIN" -Xmx1g -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
