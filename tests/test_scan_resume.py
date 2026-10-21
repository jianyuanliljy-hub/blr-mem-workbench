"""扫描续跑必须复核真实结果，不能只信任旧完成状态。"""

import json

import pytest

from blr_rm.config import defaults
from blr_rm.data import generate
from blr_rm.scan import scan
from blr_rm.status import has_failures
from blr_rm.storage import read_json


@pytest.fixture
def short_scan(tmp_path):
    dataset = generate({**defaults(1), "noise_fraction": 0.05}, tmp_path / "data", plots=False)
    destination = tmp_path / "scan"
    original = scan(dataset, destination, {"alpha": [0.2]}, {"max_iterations": 1})
    assert original["points"][0]["check"]["checks"]["numerical_convergence"] == "FAIL"
    return dataset, destination, original


def resume(dataset, destination):
    return scan(dataset, destination, {"alpha": [0.2]}, {"max_iterations": 1}, resume=True)


def test_resume_retains_actual_numerical_failure(short_scan):
    dataset, destination, original = short_scan
    current = resume(dataset, destination)
    assert current == original
    assert has_failures(current)


def test_resume_rejects_completed_receipt_without_result(short_scan, tmp_path):
    dataset, destination, _ = short_scan
    missing = tmp_path / "missing_result"
    missing.mkdir()
    for name in ("scan.json", "point_0000.json"):
        (missing / name).write_bytes((destination / name).read_bytes())
    with pytest.raises(ValueError, match="缺少结果目录"):
        resume(dataset, missing)
    assert not (missing / "complete.json").exists()


def test_resume_rejects_stale_pass_in_receipt_and_preserves_evidence(short_scan):
    dataset, destination, _ = short_scan
    path = destination / "point_0000.json"
    row = read_json(path)
    row["check"]["checks"]["numerical_convergence"] = "PASS"
    path.write_text(json.dumps(row), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="检测收据与当前结果不一致"):
        resume(dataset, destination)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field", ["index", "config", "state"])
def test_resume_rejects_receipt_identity_mismatch(short_scan, field):
    dataset, destination, _ = short_scan
    path = destination / "point_0000.json"
    row = read_json(path)
    row[field] = {"index": 1, "config": {"alpha": 9.0}, "state": "UNKNOWN"}[field]
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="收据与协议不匹配"):
        resume(dataset, destination)


@pytest.mark.parametrize("field,value", [("solver_config", {}), ("error_floor", [0.5, 0.5])])
def test_resume_rejects_result_protocol_mismatch(short_scan, field, value):
    dataset, destination, _ = short_scan
    path = destination / "point_0000/result.json"
    manifest = read_json(path)
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="配置或误差下限不同"):
        resume(dataset, destination)


@pytest.mark.parametrize("grid", [[], {"alpha": [[0.2]]}, {"alpha": [True]}, {"alpha": [float("inf")]}])
def test_malformed_grid_is_rejected_before_creating_output(tmp_path, grid):
    dataset = generate({**defaults(1), "noise_fraction": 0.05}, tmp_path / "data", plots=False)
    output = tmp_path / "bad_scan"
    with pytest.raises(ValueError, match="扫描参数|正数列表"):
        scan(dataset, output, grid)
    assert not output.exists()
