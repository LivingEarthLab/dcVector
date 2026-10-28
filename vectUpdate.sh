#!/bin/bash
# This file is part of dcVector.
#
# Copyright (c) 2025-2026 Sébastien Chognard
# Copyright (c) 2025-2026 University of Geneva
# SPDX-License-Identifier: Apache-2.0
#
# vectUpdate.sh — installs the dcVector plugin into a datacube (ODC) package.
#
# Usage:
#   ./vectUpdate.sh                      # detects datacube with $PYTHON (default: python)
#   ./vectUpdate.sh /path/to/datacube
#   PYTHON=/opt/conda/bin/python ./vectUpdate.sh
#   EXPECTED=1.9 ./vectUpdate.sh         # expected datacube version (prefix accepted)
#   FORCE=1 ./vectUpdate.sh              # skips the version check

set -e  # stop on the first failing command
set -o pipefail

# The plugin files are copied with relative paths: move to the script
# directory, whatever the current directory.
cd "$(dirname "$0")"

# ----------- Parameters -----------
PYTHON="${PYTHON:-python}"
# datacube version the patched files were written for
# (Cube-in-a-Box v1.0.0, https://github.com/LivingEarthLab/cube-in-a-box → datacube 1.9.14).
# A value of "1.9" accepts any 1.9.x; "1.9.14" accepts only that version.
EXPECTED="${EXPECTED:-1.9.14}"
FORCE="${FORCE:-0}"

# ----------- Detection of datacube with $PYTHON -----------
detectedDc=$("$PYTHON" -c "import datacube, os; print(os.path.dirname(datacube.__file__))" 2>/dev/null) || detectedDc=""

if [ -n "$1" ]; then
  pathDc="${1%/}"
else
  if [ -z "$detectedDc" ]; then
    echo "Error: cannot import datacube with '$PYTHON'."
    echo "Activate the right environment or give the path: $0 <path_to_datacube>"
    exit 1
  fi
  pathDc="$detectedDc"
fi

# ----------- Path check -----------
if [ ! -d "$pathDc" ]; then
  echo "Error: the folder $pathDc does not exist."
  exit 1
fi

# The path given as $1 must match the datacube seen by $PYTHON, otherwise
# the pip dependencies and the patched files would end up in different environments.
if [ -n "$1" ]; then
  if [ -z "$detectedDc" ]; then
    echo "⚠️  Warning: '$PYTHON' does not see any datacube package."
    echo "   The dependencies will be installed in another environment than $pathDc."
  elif [ "$(realpath "$pathDc")" != "$(realpath "$detectedDc")" ]; then
    echo "⚠️  Warning: the given path ($pathDc) differs from the datacube seen by '$PYTHON' ($detectedDc)."
    echo "   The dependencies will be installed in the environment of '$PYTHON'."
    echo "   Use PYTHON=<interpreter> to target the right environment."
  fi
fi

# ----------- Version check -----------
# Version read from the target package (not necessarily the one of $PYTHON if $1 is given).
dcVersion=$(PYTHONPATH="$(dirname "$pathDc")" "$PYTHON" -c "import datacube; print(datacube.__version__)" 2>/dev/null) || dcVersion="unknown"

echo "Python   : $(command -v "$PYTHON")"
echo "datacube : $dcVersion → $pathDc"
echo "Expected : $EXPECTED"

case "$dcVersion" in
  "$EXPECTED"|"$EXPECTED".*)
    ;;
  *)
    if [ "$FORCE" = "1" ]; then
      echo "⚠️  Version $dcVersion differs from $EXPECTED — continuing anyway (FORCE=1)."
    else
      echo "Error: datacube $dcVersion does not match the expected version ($EXPECTED)."
      echo "The replaced files are tied to a specific ODC version."
      echo "Run again with EXPECTED=<version>, or FORCE=1 if you know what you are doing."
      exit 1
    fi
    ;;
esac

# ----------- Plugin files check -----------
# Everything is checked before changing anything, to avoid a partial installation.
for f in __init__.py forJupyter.py vectors.py \
         dataset-type-schema-vect.yaml metadata-type-schema-vectors.yaml \
         core.py query.py __init__model.py dataset.py metadata.py product.py \
         _products_abstract.py _products_postgres.py _metadata_types.py; do
  if [ ! -f "./$f" ]; then
    echo "Error: plugin file ./$f not found in $(pwd)"
    exit 1
  fi
done

# ----------- Safe backup function -----------
backup_file() {
  src="$1"
  dest="$1.orig"

  if [ ! -f "$src" ]; then
    echo "Error: file $src not found"
    exit 1
  fi

  if [ -f "$dest" ]; then
    echo "Backup already exists for $src → skip"
  else
    cp "$src" "$dest"
    echo "Backup created: $dest"
  fi
}

echo "=== Backing up files ==="

backup_file "$pathDc/api/core.py"
backup_file "$pathDc/api/query.py"
backup_file "$pathDc/model/__init__.py"
backup_file "$pathDc/scripts/dataset.py"
backup_file "$pathDc/scripts/metadata.py"
backup_file "$pathDc/scripts/product.py"
backup_file "$pathDc/index/abstract/_products.py"
backup_file "$pathDc/index/postgres/_products.py"
backup_file "$pathDc/index/postgres/_metadata_types.py"

echo "=== Installing packages ==="

# The pip output (progress, warnings) is written to a log file instead of the terminal.
# It is only displayed if the installation fails.
pipLog=$(mktemp -t dcvector_pip.XXXXXX.log)
if "$PYTHON" -m pip install -q --disable-pip-version-check leafmap rasterstats hvplot geoviews joblib > "$pipLog" 2>&1; then
  echo "Packages installed."
  rm -f "$pipLog"
else
  echo "Error: the installation of the Python packages failed. pip output:"
  cat "$pipLog"
  echo "(log kept in $pipLog)"
  exit 1
fi

echo "=== Copying the new files ==="

# Copy a file and make it readable by all users: the script may run as root,
# while Jupyter runs as a regular user who must be able to import the files.
deploy() {
  cp "$1" "$2"
  chmod 644 "$2"
}

mkdir -p "$pathDc/vectors"
chmod 755 "$pathDc/vectors"

deploy ./__init__.py "$pathDc/vectors/__init__.py"
deploy ./forJupyter.py "$pathDc/vectors/forJupyter.py"
deploy ./vectors.py "$pathDc/vectors/vectors.py"

deploy ./dataset-type-schema-vect.yaml "$pathDc/model/schema/dataset-type-schema-vect.yaml"
deploy ./metadata-type-schema-vectors.yaml "$pathDc/model/schema/metadata-type-schema-vectors.yaml"

deploy ./core.py "$pathDc/api/core.py"
deploy ./query.py "$pathDc/api/query.py"
deploy ./__init__model.py "$pathDc/model/__init__.py"
deploy ./dataset.py "$pathDc/scripts/dataset.py"
deploy ./metadata.py "$pathDc/scripts/metadata.py"
deploy ./product.py "$pathDc/scripts/product.py"
deploy ./_products_abstract.py "$pathDc/index/abstract/_products.py"
deploy ./_products_postgres.py "$pathDc/index/postgres/_products.py"
deploy ./_metadata_types.py "$pathDc/index/postgres/_metadata_types.py"

echo "=== Installation completed successfully ✅ ==="
