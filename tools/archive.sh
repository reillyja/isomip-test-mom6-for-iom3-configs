#!/usr/bin/bash
# Copyright 2025 ACCESS-NRI and contributors. SPDX-License-Identifier: Apache-2.0
# Local copy of om3-scripts/payu_config/archive.sh; helper paths are quoted.
set -euo pipefail
archive_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/archive_scripts" && pwd)"
python3 "$archive_scripts_dir/standardise_mom_filenames.py"
python3 "$archive_scripts_dir/archive_esmf_streams.py"
