#!/usr/bin/env bash
set -euo pipefail
task_root=/volume/wzhang/mesh-research-workspace/micmac
cd "$task_root"
git rev-parse HEAD > .lab/build_source_commit.txt
git diff HEAD --binary > .lab/build_source_changes.patch
git fsck --connectivity-only
cmake -S . -B build-local -DCMAKE_BUILD_TYPE=Release -DWERROR=OFF -DWITH_QT5=OFF -DCUDA_ENABLED=OFF -DWITH_OPENCL=OFF
nice -n 10 cmake --build build-local --parallel 32
cmake --install build-local
bin/mm3d > .lab/mm3d_commands.txt
date -u +MICMAC_BUILD_READY=%Y-%m-%dT%H:%M:%SZ
