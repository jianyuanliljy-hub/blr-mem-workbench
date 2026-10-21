"""界面与命令行共用同一组业务函数。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .status import has_failures
from .storage import canonical, save_json


def parser():
    root = argparse.ArgumentParser(
        prog="blr-rm", description="一维/二维联合最大熵回声映射；帮助和文档见 README.md"
    )
    root.add_argument("--version", action="version", version=__import__("blr_rm").__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("generate", "batch"):
        cmd = commands.add_parser(name, help="生成单例数据" if name == "generate" else "批量生成数据")
        cmd.add_argument("--config", type=Path)
        cmd.add_argument("--dimension", type=int, choices=(1, 2), default=1)
        cmd.add_argument("--seed", type=int)
        cmd.add_argument("--noise", type=float, help="相对变异幅度的噪声标准差；0 为无噪声")
        cmd.add_argument("--out", type=Path, required=True)
        if name == "batch":
            cmd.add_argument("--count", type=int, required=True)
            cmd.add_argument("--resume", action="store_true")
        else:
            cmd.add_argument("--no-plots", action="store_true")
    for name in ("optimize", "scan"):
        cmd = commands.add_parser(
            name, help="联合 MEM 反演" if name == "optimize" else "完整超参数网格扫描，不自动选最优"
        )
        cmd.add_argument("--data", type=Path, required=True)
        cmd.add_argument("--config", type=Path, help="优化参数 JSON")
        cmd.add_argument("--error-floor", type=float, nargs=2, metavar=("C", "L"))
        cmd.add_argument("--out", type=Path, required=True)
        if name == "scan":
            cmd.add_argument("--grid", type=Path, required=True)
            cmd.add_argument("--resume", action="store_true")
    cmd = commands.add_parser("check", help="独立检测数据或反演结果")
    cmd.add_argument("--data", type=Path, required=True)
    cmd.add_argument("--result", type=Path)
    cmd.add_argument("--out", type=Path, help="可选，新建 JSON 检测收据")
    cmd = commands.add_parser("report", help="生成离线图表和 HTML 报告")
    cmd.add_argument("--data", type=Path, required=True)
    cmd.add_argument("--result", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cmd = commands.add_parser("benchmark", help="冻结协议并执行软件验证矩阵")
    cmd.add_argument("--profile", choices=("smoke", "validation"), default="smoke")
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--resume", action="store_true")
    commands.add_parser("gui", help="打开图形界面")
    return root


def dispatch(args):
    from .benchmark import run_benchmark
    from .config import read_config
    from .data import batch_generate, generate
    from .detector import inspect_dataset, inspect_result
    from .report import write_result_report
    from .scan import scan
    from .solver import optimize

    if args.command in ("generate", "batch"):
        cfg = read_config(args.config, args.dimension)
        if args.noise is not None:
            cfg["noise_fraction"] = args.noise
        if args.seed is not None:
            cfg["seed"] = args.seed
        if args.command == "batch":
            return batch_generate(cfg, args.count, args.out, args.resume)
        return {"output": str(generate(cfg, args.out, not args.no_plots))}
    if args.command in ("optimize", "scan"):
        cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
        if args.command == "scan":
            grid = json.loads(args.grid.read_text(encoding="utf-8"))
            return scan(args.data, args.out, grid, cfg, args.error_floor, args.resume)
        return optimize(args.data, args.out, cfg, args.error_floor)
    if args.command == "check":
        result = inspect_result(args.data, args.result) if args.result else inspect_dataset(args.data)
        if args.out:
            save_json(args.out, result)
        return result
    if args.command == "report":
        return {"report": write_result_report(args.data, args.result, args.out)}
    if args.command == "benchmark":
        return run_benchmark(
            args.out,
            args.profile,
            args.resume,
            progress=lambda value: print(value, file=sys.stderr, flush=True),
        )
    from .gui import main as gui_main

    return gui_main()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        if result is not None:
            print(canonical(result), end="")
        if has_failures(result):
            return 2
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
