"""完整枚举超参数；不以模拟真值选参，不隐式重试失败点。"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

from .config import resolved_solver
from .detector import inspect_result
from .solver import load_observations, optimize
from .storage import environment, read_json, save_json


def _check_saved_point(dataset, point, config, error_floor):
    if not point.is_dir():
        raise ValueError(f"已完成的扫描点缺少结果目录: {point.name}")
    run = read_json(point / "result.json")
    expected_floor = list(error_floor) if error_floor else None
    if run.get("solver_config") != config or run.get("error_floor") != expected_floor:
        raise ValueError(f"已有扫描点的配置或误差下限不同: {point.name}")
    return inspect_result(dataset, point, include_truth=False)


def scan(dataset, output, grid: dict, base_config: dict | None = None, error_floor=None, resume=False):
    meta, _ = load_observations(dataset)
    allowed = (
        {"alpha", "stiffness_weight"}
        if meta["dimension"] == 1 and (base_config or {}).get('engine') != 'autumn_normalized_joint_mem'
        else {"alpha_map", "alpha_c", "alpha_lbg", "smoothness_ratio"}
    )
    if not isinstance(grid, dict) or not grid or set(grid) - allowed:
        raise ValueError(f"扫描参数只支持 {sorted(allowed)}")
    count = 1
    for name, values in grid.items():
        if (
            not isinstance(values, list)
            or not values
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                for value in values
            )
            or len(set(values)) != len(values)
        ):
            raise ValueError(f"{name} 必须为非空、无重复的有限正数列表")
        count *= len(values)
    if count > 1024:
        raise ValueError("首版单次扫描最多 1024 点；请显式分批，避免误启动巨量计算")
    base_config = resolved_solver(meta["dimension"], base_config)
    keys = sorted(grid)
    configs = [
        resolved_solver(meta["dimension"], {**base_config, **dict(zip(keys, point))})
        for point in itertools.product(*(grid[key] for key in keys))
    ]
    output = Path(output)
    protocol = {
        "schema_version": 1,
        "observation_id": meta["observation_id"],
        "grid": grid,
        "configs": configs,
        "error_floor": list(error_floor) if error_floor else None,
        "selection": "NONE_PURE_SCAN",
        "environment": environment(),
    }
    if resume:
        previous = read_json(output / "scan.json")
        if any(
            previous[key] != protocol[key]
            for key in ("schema_version", "observation_id", "configs", "error_floor")
        ):
            raise ValueError("续跑协议不匹配")
        if previous["environment"]["source_sha256"] != protocol["environment"]["source_sha256"]:
            raise ValueError("代码已变化；不能把新实现静默混入原扫描")
    else:
        output.mkdir(parents=True, exist_ok=False)
        save_json(output / "scan.json", protocol)
    rows = []
    for index, cfg in enumerate(configs):
        point = output / f"point_{index:04d}"
        receipt = output / f"point_{index:04d}.json"
        if receipt.exists():
            row = read_json(receipt)
            if not resume:
                raise FileExistsError(str(receipt))
            if (
                not isinstance(row, dict)
                or row.get("index") != index
                or row.get("config") != cfg
                or row.get("state") not in ("COMPLETED", "FAILED")
            ):
                raise ValueError(f"扫描点收据与协议不匹配: {receipt.name}")
            if row["state"] == "COMPLETED":
                checked = _check_saved_point(dataset, point, cfg, error_floor)
                cached = row.get("check")
                if not isinstance(cached, dict) or any(
                    cached.get(key) != checked[key]
                    for key in ("checks", "observation_id", "optimizer_success", "optimizer_history_warning")
                ):
                    raise ValueError(f"扫描点检测收据与当前结果不一致: {receipt.name}")
                # 汇总使用本次独立复核结果；历史收据保留，不静默改写。
                row = {**row, "check": checked}
            rows.append(row)
            continue
        try:
            if point.exists():
                if not resume:
                    raise FileExistsError(str(point))
                checked = _check_saved_point(dataset, point, cfg, error_floor)
            else:
                checked = optimize(dataset, point, cfg, error_floor)
            row = {"index": index, "config": cfg, "state": "COMPLETED", "check": checked}
        except (ValueError, OSError, RuntimeError) as error:
            row = {"index": index, "config": cfg, "state": "FAILED", "error": str(error)}
        save_json(receipt, row)
        rows.append(row)
    summary = {
        "schema_version": 1,
        "selection": "NONE_PURE_SCAN",
        "count": len(rows),
        "points": rows,
        "failures": sum(row["state"] == "FAILED" for row in rows),
    }
    if not (output / "complete.json").exists():
        save_json(output / "complete.json", summary)
    return summary
