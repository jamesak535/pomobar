#!/bin/bash
set -e

echo "🍅 Building PomoBar..."

# Clean previous builds
rm -rf build dist .eggs

# Build the .app bundle
python setup.py py2app

# Point _objc.so to Apple's system libffi
install_name_tool -change \
    @rpath/libffi.8.dylib \
    /usr/lib/libffi.dylib \
    "dist/PomoBar.app/Contents/Resources/lib/python3.12/lib-dynload/objc/_objc.so"

# Re-sign _objc.so individually first, then the whole app
codesign --force --sign - "dist/PomoBar.app/Contents/Resources/lib/python3.12/lib-dynload/objc/_objc.so"
codesign --force --deep --sign - "dist/PomoBar.app"

echo ""
echo "✅ Build complete: dist/PomoBar.app"
echo "   Run with: open \"dist/PomoBar.app\""