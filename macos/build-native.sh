#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $(uname -s) != Darwin || $(uname -m) != x86_64 ]]; then
    echo 'Build on an Intel Mac with Xcode Command Line Tools.' >&2
    exit 1
fi
xcrun clang -arch x86_64 -mmacosx-version-min=12.0 -fobjc-arc -fblocks -Wall -Wextra \
  -framework Foundation -framework AppKit -framework CoreGraphics \
  linux/monitorize/macos/native/display.m -o linux/monitorize/macos/native/monitorize-display
file linux/monitorize/macos/native/monitorize-display
