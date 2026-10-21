#!/bin/sh
set -eu
package_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -d "$package_dir/BLR MEM Workbench.app" ]; then
    exec /usr/bin/open -n "$package_dir/BLR MEM Workbench.app" --args --dimension 2
fi
if [ -x "$package_dir/.venv/bin/python" ]; then
    export PYTHONPATH="$package_dir/src${PYTHONPATH:+:$PYTHONPATH}"
    exec "$package_dir/.venv/bin/python" "$package_dir/tools/frozen_entry.py" --dimension 2
fi
printf '%s\n' '请使用 macOS 应用包，或按 docs/USAGE_ZH.md 创建 .venv 后启动。'
exit 1
