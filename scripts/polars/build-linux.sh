#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 5 ]]; then
  echo "Usage: build-linux.sh SOURCE.tar.gz RUST.tar.gz NOTICES_DIR DEPENDENCY_LIBRARY OUTPUT_DIR" >&2
  exit 2
fi
source_archive=$(realpath "$1")
rust_archive=$(realpath "$2")
notices=$(realpath "$3")
export R_LIBS_USER=$(realpath "$4")
mkdir -p "$5"
output=$(realpath "$5")

. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_CODENAME" == noble && "$(uname -m)" == x86_64 ]]
Rscript -e 'stopifnot(getRversion() == "4.5.2", packageVersion("rlang") == "1.3.0", packageVersion("S7") == "0.2.2")'

build=$(mktemp -d)
cd "$build"
tar -xzf "$source_archive" --no-same-owner
tar -xzf "$rust_archive" --no-same-owner
mkdir -p polars/inst/licenses library
cp "$notices"/*.txt polars/inst/licenses/
export LIBR_POLARS_BUILD=false
export LIBR_POLARS_PATH="$build/libr_polars.a"
test -s "$LIBR_POLARS_PATH"
R CMD INSTALL --build --library="$build/library" polars
cp polars_*_R_x86_64-pc-linux-gnu.tar.gz "$output/"
printf 'Built with R %s on %s (%s)\n' "$(Rscript -e 'cat(as.character(getRversion()))')" "$PRETTY_NAME" "$(uname -m)"
