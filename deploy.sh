#!/bin/bash
set -euo pipefail

# CONFIG
PACKAGE_NAME="aiomqttc"
DIST_DIR="dist"

# Check if uploading to TestPyPI
REPOSITORY="pypi"
if [[ "${1:-}" == "test" ]]; then
  REPOSITORY="testpypi"
  echo "🚧 Uploading to TestPyPI..."
else
  echo "🚀 Uploading to PyPI..."
fi

# Ensure tools are installed
echo "📦 Ensuring build & twine are installed via uv..."
uv pip install --system build twine

# Clean previous builds
echo "🧹 Cleaning old builds..."
rm -rf "$DIST_DIR" *.egg-info

# Build sdist and wheel
echo "🔨 Building distributions..."
python -m build

# Check package
echo "🔍 Checking package integrity..."
twine check $DIST_DIR/*

# Upload
echo "☁️ Uploading to $REPOSITORY..."
twine upload --repository "$REPOSITORY" $DIST_DIR/*

echo "✅ Done."