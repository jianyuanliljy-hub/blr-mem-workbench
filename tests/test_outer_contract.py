"""Regression checks for frozen-default update and duplicate evaluations."""
import inspect

import numpy as np

from blr_rm._vendor.mem2d import MEM2DProblem, reconstruct_mem2d


def test_unconverged_inner_does_not_update_defaults(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('blr_rm._vendor.mem2d.minimize', lambda f, x, **kw:
                        SimpleNamespace(x=x, nit=0, success=False))
    problem = MEM2DProblem(
        np.arange(-2., 7.), np.full(9, 10.), np.ones(9),
        np.arange(5.), np.tile(np.arange(5.) + 3., (2, 1)), np.ones((2, 5)),
        np.array([-1., 1.]), np.arange(3.),
    )
    result = reconstruct_mem2d(problem, {
        "default_iterations": 4, "coordinate_cycles": 1,
        "optimizer_maxiter": 1, "test_threshold": 1e-30,
        "q_gradient_threshold": 1e-30,
    })
    assert result.diagnostics["outer_iterations"] == 1
    assert not result.diagnostics["final_inner_converged"]


def test_no_repeated_full_evaluation_at_cycle_check():
    assert "obj_full(w)[" not in inspect.getsource(reconstruct_mem2d)
