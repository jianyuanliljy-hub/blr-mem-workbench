"""Adapt the preserved autumn solver without executing its plotting/main section.

Each fit owns a namespace; environment-dependent initialization is serialized.
No simulated truth file is read. NPZ observations are translated to the original
four-CSV contract in a temporary directory, never written into the dataset.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import tempfile
import threading

import numpy as np

_LOCK = threading.Lock()
ENGINE = 'autumn_normalized_joint_mem'


def fit(meta, obs, cfg, c_err, l_err):
    from .data import forward_matrix

    if obs['delays'][0] != 0:
        raise ValueError('Autumn solver requires delay_min=0; it does not silently change the delay grid')

    with _LOCK, tempfile.TemporaryDirectory(prefix='blr_autumn_') as temp:
        temp = Path(temp)
        mask = obs['time_mask']
        tables = {
            'C_data': (np.c_[obs['t_c'], obs['c_obs']], 'time_days,continuum_flux'),
            'C_err': (np.c_[obs['t_c'], c_err], 'time_days,continuum_error'),
            'L_data': (np.c_[obs['t_l'][mask], obs['l_obs'][:, mask].T],
                       'time_days,' + ','.join(f'flux_{v:.17g}' for v in obs['velocities'])),
            'L_err': (np.c_[obs['t_l'][mask], l_err[:, mask].T],
                      'time_days,' + ','.join(f'error_{v:.17g}' for v in obs['velocities'])),
        }
        for name, (table, header) in tables.items():
            np.savetxt(temp / f'{name}.csv', table, delimiter=',', header=header, comments='')
        env = {
            'MEM_CONTINUUM_CSV': str(temp/'C_data.csv'),
            'MEM_CONTINUUM_ERR_CSV': str(temp/'C_err.csv'),
            'MEM_LINE_CSV': str(temp/'L_data.csv'),
            'MEM_LINE_ERR_CSV': str(temp/'L_err.csv'),
            'MEM_TAU_PIXELS': str(len(obs['delays'])),
            'MEM_DELAY_MAX_DAYS': str(obs['delays'][-1]),
            'MEM_C0_MODE': 'simulation_truth', 'MEM_C0_TRUTH': str(meta['c0']),
            'MEM_GRADIENT_BACKEND': cfg['gradient_backend'],
            'MEM_USE_JAX_JIT': str(int(cfg['jax_jit'])),
            'MEM_JAX_DEVICE': cfg['jax_device'],
            'MEM_USE_NUMBA': str(int(cfg['use_numba'])),
            'MEM_GAP_CURVATURE_WEIGHT': '0',
            'MEM_RESEARCH_ALLOW_INCOMPLETE': '0',
            'MEM_ALPHA_MAP': str(cfg.get('alpha_map', cfg.get('alpha', .2))),
            'MEM_ALPHA_C': str(cfg.get('alpha_c', 1200.)),
            'MEM_ALPHA_LBG': str(cfg.get('alpha_lbg', .02)),
            'MEM_SMOOTHNESS_RATIO': str(cfg.get('smoothness_ratio', 1.)),
            'MEM_JAX_CACHE_DIR': '',
        }
        previous = {key: os.environ.get(key) for key in env}
        try:
            os.environ.update(env)
            source = Path(__file__).with_name('autumn')/'023_0821.py'
            if not source.exists() and getattr(sys, 'frozen', False):
                source = Path(sys._MEIPASS)/'autumn/023_0821.py'
            # Explicit boundary in the vendored baseline: retain definitions and
            # initialization, but never run its GUI-oriented main/plot pipeline.
            text = source.read_text(encoding='utf-8')
            marker = '# ---- 执行 Adams warm-up (如果启用) ----'
            if text.count(marker) != 1:
                raise RuntimeError('Autumn source boundary changed; adapter must be reviewed')
            ns = {'__file__': str(source), '__name__': 'blr_autumn_fit'}
            exec(compile(text.split(marker)[0], str(source), 'exec'), ns)
            if not np.allclose(ns['t_C'], obs['t_c'], rtol=0, atol=1e-10):
                raise ValueError('Current NPZ adapter requires a complete regular C grid')
            amap = cfg.get('alpha_map', cfg.get('alpha', .2))
            ac = cfg.get('alpha_c', 1200.)
            abg = cfg.get('alpha_lbg', .02)
            start = None
            if cfg['adam_steps']:
                start, _ = ns['adam_warmup'](
                    ns['w0_init'], amap, ac, abg, n_steps=cfg['adam_steps'], step_size=.03)
            p, c, bg, _, history = ns['mem_2d_reconstruction_corrected'](
                amap, ac, abg, cfg.get('smoothness_ratio', 1.),
                cfg.get('optimizer_maxiter', cfg.get('max_iterations', 800)),
                cfg.get('default_iterations', 1000),
                cfg.get('default_change_tolerance', .01), cfg.get('default_damping', .5),
                cfg.get('test_threshold', 1e-5), cfg.get('q_gradient_threshold', .003),
                w_start=start)
            cn, ln = ns['C_NORMALIZATION'], ns['L_NORMALIZATION']
            p, c, bg = p*ln/cn, c*cn, bg*ln
            pred = p @ forward_matrix(obs['t_c'], c, obs['t_l'], obs['delays'], meta['c0']).T
            pred = pred * np.diff(obs['delays'])[0] + bg[:, None]
            arrays = dict(psi=p, continuum=c, l_bg=bg, l_pred=pred,
                          default_map=ns['q_flat'].reshape(p.shape)*ln/cn,
                          default_continuum=ns['q_C']*cn,
                          default_background=ns['q_L_bg']*ln,
                          c_error_used=c_err, l_error_used=l_err)
            point = np.r_[p.ravel()*cn/ln, c/cn, bg/ln]
            objective, _ = ns['objective_Q_with_manual_gradient'](point, amap, ac, abg)
            diag = dict(optimizer_success=all(history['optimizer_success']),
                        final_inner_converged=history['research_inner_converged'],
                        final_default_converged=history['research_default_converged'],
                        objective_F=float(objective), objective_Q=-float(objective),
                        final_default_change=float(history['default_change'][-1]),
                        objective_convention='mean_chi2_C+mean_chi2_L-sum(alpha*S/sum(default))',
                        continuum_errors_rescaled=False, defaults_updated=True,
                        engine=ENGINE, gradient_backend=cfg['gradient_backend'],
                        jax_device_requested=cfg['jax_device'],
                        jax_device_actual=str(ns.get('selected_devices', ['not_used'])[0]),
                        normalization_C=cn, normalization_L=ln)
            records = [{key: value[i] for key, value in history.items() if isinstance(value, list)}
                       for i in range(len(history['default_change']))]
            for i, row in enumerate(records):
                row.update(outer=i+1, reduced_chi2_C=row['chi2_C'], reduced_chi2_L=row['chi2_L'])
            return arrays, diag, records
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
