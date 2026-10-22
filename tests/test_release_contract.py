"""Regression checks for the files/entry points omitted by manual uploads."""
from pathlib import Path

import pytest

from blr_rm.config import AUTUMN_ENGINE, read_config, resolved_solver, solver_defaults
from blr_rm.data import generate
from blr_rm.detector import inspect_dataset
from blr_rm.report import write_result_report
from blr_rm.scan import scan
from blr_rm.solver import optimize
from blr_rm.storage import read_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('dimension', [1, 2])
def test_shipped_presets_generate_optimize_scan_and_report(tmp_path, dimension):
    cfg = read_config(ROOT/f'{dimension}D/generate_noisy.json', dimension)
    data = generate(cfg, tmp_path/'data')
    assert inspect_dataset(data)['generator_forward'] == 'PASS'
    params = read_json(ROOT/f'{dimension}D/mem_defaults.json')
    assert resolved_solver(dimension, params)['engine'] == solver_defaults(dimension)['engine'] == AUTUMN_ENGINE
    result = tmp_path/'fit'
    check = optimize(data, result, params)
    assert all(value == 'PASS' for value in check['checks'].values())
    report = write_result_report(data, result, tmp_path/'report')
    assert Path(report).is_file()
    # One real scan point plus resume exercises the published configuration route.
    grid = {'alpha_map': [params['alpha_map']]}
    summary = scan(data, tmp_path/'scan', grid, params)
    assert summary['failures'] == 0
    assert summary['points'][0]['check']['checks']['numerical_convergence'] == 'PASS'
    assert scan(data, tmp_path/'scan', grid, params, resume=True) == summary


def test_autumn_source_is_in_installed_package():
    import blr_rm.autumn
    source = Path(blr_rm.autumn.__file__).with_name('023_0821.py')
    assert source.is_file()
    assert 'def mem_2d_reconstruction_corrected' in source.read_text(encoding='utf-8')


def test_old_ignored_options_are_rejected():
    with pytest.raises(ValueError, match='未识别'):
        resolved_solver(1, {'max_iterations': 1})
