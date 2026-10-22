"""Run real fits with different autumn backends; preserve every failure."""
import contextlib
import json
from pathlib import Path

import numpy as np

from blr_rm.solver import optimize
from blr_rm.storage import load_arrays


def main():
    root = Path('evidence/autumn_backends')
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    for dimension in (1, 2):
        data = Path('evidence/review_smoke/data')/f'case_{dimension-1:04d}'
        for name, overrides in (
            ('manual', {}),
            ('numba', {'use_numba': True}),
            ('jax_plain', {'gradient_backend': 'jax', 'jax_jit': False}),
            ('jax_jit', {'gradient_backend': 'jax', 'jax_jit': True}),
        ):
            output = root/f'{dimension}D_{name}'
            row = {'dimension': dimension, 'backend': name}
            with (root/f'{dimension}D_{name}.log').open('x', encoding='utf-8') as log:
                try:
                    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                        check = optimize(data, output, {'engine':'autumn_normalized_joint_mem', **overrides})
                    arrays = load_arrays(output/'solution.npz')
                    reference = load_arrays(root/f'{dimension}D_manual'/'solution.npz')
                    row.update(state='COMPLETED', checks=check['checks'],
                               compute_seconds=check['compute_seconds'],
                               psi_relative_to_manual=float(np.linalg.norm(arrays['psi']-reference['psi'])/
                                   max(np.linalg.norm(reference['psi']), 1e-30)))
                except Exception as error:
                    row.update(state='FAILED', error=str(error))
            rows.append(row)
            print(row, flush=True)
            (root/'summary.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
