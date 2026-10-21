"""界面和命令行使用同一套结果状态解释。"""

CHECK_LABELS = {
    "integrity": "文件与数组",
    "forward_consistency": "独立前向模型",
    "numerical_convergence": "最终一阶条件",
    "floating_default_stability": "浮动默认图像稳定性",
    "generator_forward": "生成数据前向模型",
    "noiseless_identity": "无噪声真值一致性",
}


def result_lines(result):
    """面向使用者的摘要；完整数值记录继续保存在结果和日志中。"""
    lines = []
    checks = {**{key: result[key] for key in CHECK_LABELS if key in result}, **result.get("checks", {})}
    for key, value in checks.items():
        if key in CHECK_LABELS:
            label = {
                "PASS": "通过",
                "FAIL": "未通过",
                "WARN": "需查看",
                "NOT_APPLICABLE_FIXED_DEFAULT": "固定默认图像，无外层更新",
            }.get(value, value)
            lines.append(f"{CHECK_LABELS[key]}：{label}")
    if result.get("optimizer_history_warning", "NONE") != "NONE":
        lines.append("优化历史：至少一次中间求解报告失败；请结合最终一阶条件判断。")
    metrics = result.get("truth_metrics", {})
    if metrics:
        lines += [
            f"形状归一化均方误差（shape NMSE）：{metrics['shape_nmse']:.5g}",
            f"时延质心偏差：{metrics['lag_centroid_error_days']:.5g} day",
        ]
    return lines


def has_failures(result):
    if not isinstance(result, dict):
        return False
    if any(value == "FAIL" for value in result.get("checks", {}).values()):
        return True
    if result.get("generator_forward") == "FAIL" or result.get("noiseless_identity") == "FAIL":
        return True
    if (
        result.get("failures", 0)
        or result.get("execution_failures", 0)
        or result.get("numerical_failures", 0)
    ):
        return True
    if any(row.get("numerical_pass", 0) < row["planned"] for row in result.get("groups", [])):
        return True
    return any(
        row.get("state") == "FAILED" or has_failures(row.get("check")) for row in result.get("points", [])
    )


def has_warnings(result):
    if not isinstance(result, dict):
        return False
    if any(value == "WARN" for value in result.get("checks", {}).values()):
        return True
    if result.get("optimizer_history_warning", "NONE") != "NONE" or result.get("warning_count", 0):
        return True
    return any(
        row.get("floating_default_warn", 0) or row.get("optimizer_history_warning", 0)
        for row in result.get("groups", [])
    )
