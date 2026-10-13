#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt_options=(-o Acquire::http::Proxy=http://127.0.0.1:17995 -o Acquire::https::Proxy=http://127.0.0.1:17995 -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources -o Dir::Etc::sourceparts=- -o DPkg::Lock::Timeout=120)
apt-get "${apt_options[@]}" update
apt-get "${apt_options[@]}" install -y --no-upgrade build-essential libx11-dev imagemagick libimage-exiftool-perl exiv2 proj-bin libproj-dev gdal-bin python3-gdal python3-numpy
date -u +DEPENDENCIES_READY=%Y-%m-%dT%H:%M:%SZ
