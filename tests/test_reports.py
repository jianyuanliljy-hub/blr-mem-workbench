import shutil

import pytest

from blr_rm.config import defaults
from blr_rm.data import generate
from blr_rm.report import write_result_report
from blr_rm.solver import optimize
from blr_rm.storage import read_json


@pytest.mark.parametrize("dimension", [1, 2])
def test_offline_report_with_and_without_truth_preserves_numerical_state(tmp_path, dimension):
    data = generate({**defaults(dimension), "noise_fraction": 0.05}, tmp_path / "data", plots=False)
    result = tmp_path / "result"
    original = optimize(data, result)
    observed_only = tmp_path / "observed_only"
    observed_only.mkdir()
    for name in ("dataset.json", "observations.npz"):
        shutil.copy2(data / name, observed_only / name)
    for source, name, has_truth in ((data, "full", True), (observed_only, "no_truth", False)):
        output = tmp_path / name
        report = write_result_report(source, result, output)
        saved = read_json(output / "check.json")
        assert saved["checks"] == original["checks"]
        assert ("truth_metrics" in saved) is has_truth
        document = (output / "report.html").read_text()
        assert "最终一阶条件" in document
        assert (output / "diagnostics.png").stat().st_size > 1000
        assert (output / "reconstruction.png").stat().st_size > 1000
        assert report == str(output / "report.html")
        if dimension == 2:
            assert "有数值警告" in document
            assert (output / "response.png").stat().st_size > 1000
            assert (
                read_json(output / "default_map_diagnostic.json")["purpose"]
                == "EXPLORATORY_ONLY_NO_CHANGE_TO_ACCEPTANCE"
            )
