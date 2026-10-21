import json

import pytest

from blr_rm.cli import main
from blr_rm.config import defaults, read_config, resolved_generator, resolved_solver
from blr_rm.status import result_lines


@pytest.mark.parametrize("raw", [[], [1], "text", 3, None, True])
def test_non_object_config_has_actionable_error(raw):
    for resolve in (resolved_generator, lambda value: resolved_solver(1, value)):
        if raw is None and resolve is not resolved_generator:
            continue
        with pytest.raises(ValueError, match="JSON 对象"):
            resolve(raw)


@pytest.mark.parametrize(
    "key,value",
    [
        ("cadence_days", "1"),
        ("duration_days", None),
        ("noise_fraction", True),
        ("psd_beta", []),
        ("dimension", True),
    ],
)
def test_bad_field_type_is_rejected_before_computation(key, value):
    with pytest.raises(ValueError):
        resolved_generator({key: value})


def test_partial_preset_and_windows_utf8_bom_are_supported(tmp_path):
    path = tmp_path / "预设.json"
    path.write_text(json.dumps({"dimension": 2, "noise_fraction": 0.05}), encoding="utf-8-sig")
    assert read_config(path) == {**defaults(2), "noise_fraction": 0.05}


def test_cli_bad_json_schema_returns_readable_error(tmp_path, capsys):
    path = tmp_path / "config.json"
    path.write_text("[]")
    assert main(["generate", "--config", str(path), "--out", str(tmp_path / "unused")]) == 1
    stderr = capsys.readouterr().err
    assert "JSON 对象" in stderr
    assert "Traceback" not in stderr
    assert not (tmp_path / "unused").exists()


def test_status_keeps_final_conditions_and_history_warning_separate():
    lines = result_lines(
        {
            "checks": {"numerical_convergence": "PASS", "floating_default_stability": "WARN"},
            "optimizer_history_warning": "history failure",
        }
    )
    assert "最终一阶条件：通过" in lines
    assert "浮动默认图像稳定性：需查看" in lines
    assert any("中间求解报告失败" in line for line in lines)
