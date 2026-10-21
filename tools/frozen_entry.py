"""Windows 多入口与 macOS 应用、命令行共用的启动器。"""

import argparse
import sys
from pathlib import Path


def main():
    aliases = {
        "GenerateData": "generate",
        "BatchGenerate": "batch",
        "MEMOptimizer": "optimize",
        "Detector": "check",
        "Analysis": "report",
    }
    name = Path(sys.executable).stem
    arguments = sys.argv[1:]
    if arguments[:1] == ["--gui-flow"]:
        from blr_rm.gui_validation import run_gui_flow

        parser = argparse.ArgumentParser()
        parser.add_argument("--gui-flow", action="store_true")
        parser.add_argument("--out", type=Path, required=True)
        args = parser.parse_args(arguments)
        run_gui_flow(args.out)
        return 0
    if name == "blr-rm" or arguments[:1] == ["--cli"]:
        from blr_rm.cli import main as cli_main

        return cli_main(arguments[1:] if arguments[:1] == ["--cli"] else arguments)
    if not arguments or arguments[0].startswith("--dimension") or "--gui-smoke" in arguments:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dimension", type=int, choices=(1, 2), default=1)
        parser.add_argument("--gui-smoke", action="store_true")
        args = parser.parse_args(arguments)
        if args.gui_smoke:
            import tkinter as tk

            from blr_rm.gui import Workbench

            root = tk.Tk()
            Workbench(root, args.dimension, aliases.get(name, "generate"))
            root.after(750, root.destroy)
            root.mainloop()
            return 0
        from blr_rm.gui import main as gui_main

        gui_main(args.dimension, aliases.get(name, "generate"))
        return 0
    from blr_rm.cli import main as cli_main

    return cli_main([aliases[name], *arguments] if name in aliases else arguments)


if __name__ == "__main__":
    raise SystemExit(main())
