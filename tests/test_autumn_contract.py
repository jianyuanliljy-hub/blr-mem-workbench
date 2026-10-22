"""Scientific invariants for the autumn objective and exposed options."""
import numpy as np
import pytest

from blr_rm.config import resolved_solver
from blr_rm.detector import independent_objective_gradient


@pytest.mark.parametrize('dimension', [1, 2])
def test_autumn_gradient_physical_units(dimension):
    nv = 1 if dimension == 1 else 3
    obs = dict(t_c=np.arange(-2., 5.), t_l=np.arange(3.), delays=np.arange(3.),
               c_obs=np.linspace(9., 11., 7), l_obs=np.full((nv, 3), 5.),
               time_mask=np.array([True, False, True]))
    sol = dict(psi=np.full((nv, 3), .1), continuum=obs['c_obs']+.03,
               l_bg=np.full(nv, 5.1), default_map=np.full((nv, 3), .12),
               default_continuum=np.full(7, 10.), default_background=np.full(nv, 5.),
               c_error_used=np.full(7, .1), l_error_used=np.full((nv, 3), .2))
    cfg = resolved_solver(dimension, {'engine':'autumn_normalized_joint_mem'})
    _, analytical = independent_objective_gradient(obs, sol, cfg, 10., dimension)
    numerical = []
    for key in ('psi', 'continuum', 'l_bg'):
        for index in np.ndindex(sol[key].shape):
            x = sol[key][index]
            h = 1e-5*max(1, abs(x))
            sol[key][index] = x+h
            plus = independent_objective_gradient(obs, sol, cfg, 10., dimension)[0]['objective_F']
            sol[key][index] = x-h
            minus = independent_objective_gradient(obs, sol, cfg, 10., dimension)[0]['objective_F']
            sol[key][index] = x
            numerical.append((plus-minus)/(2*h))
    np.testing.assert_allclose(numerical, analytical, atol=1e-6, rtol=1e-5)


def test_autumn_backend_values_are_validated():
    for option in ({'jax_device':'cuda'}, {'jax_jit':'false'}, {'adam_steps':True}):
        with pytest.raises(ValueError):
            resolved_solver(2, {'engine':'autumn_normalized_joint_mem', **option})
