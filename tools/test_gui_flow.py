"""在有桌面会话的环境执行自有界面操作链。"""

import argparse
from pathlib import Path

from blr_rm.gui_validation import run_gui_flow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("evidence/gui_flow_mainloop.json"))
    args = parser.parse_args()
    run_gui_flow(args.out)


if __name__ == "__main__":
    main()
