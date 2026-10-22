"""Exercise the actual frozen Windows programs with no developer Python paths.

The receipt is only written after every required operation succeeds. Per-command
logs remain available if any command fails; failure is never converted to PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def validate(bundle, output, gui=True, accelerators=True):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    temp = output / 'temp'
    temp.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in
           ('PYTHONPATH', 'PYTHONHOME', 'TCL_LIBRARY', 'TK_LIBRARY', 'JAX_PLATFORMS')}
    env.update(TMP=str(temp), TEMP=str(temp), PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
               MPLBACKEND='Agg', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', MPLCONFIGDIR=str(temp/'matplotlib'))
    if sys.platform == 'win32':
        system = Path(os.environ.get('SystemRoot', 'C:/Windows'))
        env['PATH'] = str(system/'System32') + os.pathsep + str(system)
    records = []

    def run(arguments, allowed=(0,), timeout=240):
        result = subprocess.run(list(map(str, arguments)), cwd=output, env=env,
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        index = len(records)+1
        (output/f'command_{index:02d}.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        records.append({'arguments': list(map(str, arguments)), 'exit_code': result.returncode})
        if result.returncode not in allowed:
            raise RuntimeError(f'Frozen command {index} failed ({result.returncode}); see command_{index:02d}.log')
        return result.stdout

    cli = bundle/'blr-rm.exe'
    version = run([cli, '--version']).strip()
    if version != '0.1.0.dev2':
        raise RuntimeError(f'Unexpected executable version: {version}')
    run([cli, 'benchmark', '--profile', 'smoke', '--out', output/'smoke'])
    checks = []
    for dimension in (1, 2):
        data = output/f'smoke/data/case_{dimension-1:04d}'
        result = output/f'smoke/results/case_{dimension-1:04d}'
        checked = json.loads(run([cli, 'check', '--data', data, '--result', result]))
        assert all(value == 'PASS' for value in checked['checks'].values())
        run([cli, 'report', '--data', data, '--result', result, '--out', output/f'report_{dimension}D'])
        clean = output/f'clean_{dimension}D'
        run([cli, 'generate', '--config', bundle/f'{dimension}D/generate_clean.json', '--out', clean])
        assert json.loads(run([cli, 'check', '--data', clean]))['noiseless_identity'] == 'PASS'
        assert (clean/'truth.png').is_file()
        for resume in (False, True):
            run([cli, 'batch', '--dimension', dimension, '--count', 2, '--out', output/f'batch_{dimension}D',
                 *(['--resume'] if resume else [])])
        grid = output/f'grid_{dimension}D.json'
        grid.write_text(json.dumps({'alpha_map':[.1, .2]}), encoding='utf-8')
        for resume in (False, True):
            run([cli, 'scan', '--data', data, '--grid', grid, '--config', bundle/f'{dimension}D/mem_defaults.json',
                 '--out', output/f'scan_{dimension}D', *(['--resume'] if resume else [])], allowed=(0,2))
        scan = json.loads((output/f'scan_{dimension}D/complete.json').read_text(encoding='utf-8'))
        assert scan['count'] == 2 and scan['selection'] == 'NONE_PURE_SCAN'
        if accelerators:
            for backend, settings in (
                ('jax', {'gradient_backend':'jax', 'jax_jit':True, 'jax_device':'cpu'}),
                ('numba', {'gradient_backend':'manual', 'use_numba':True}),
            ):
                params = output/f'{dimension}D_{backend}.json'
                params.write_text(json.dumps({'engine':'autumn_normalized_joint_mem', **settings}), encoding='utf-8')
                accelerated = output/f'fit_{dimension}D_{backend}'
                run([cli, 'optimize', '--data', data, '--config', params, '--out', accelerated])
                verified = json.loads(run([cli, 'check', '--data', data, '--result', accelerated]))
                assert all(value == 'PASS' for value in verified['checks'].values())
        checks.append({'dimension':dimension, 'default_fit':checked['checks'],
                       'pure_scan_points':scan['count'], 'pure_scan_failures':scan['failures']})
    if gui:
        for name in ('GenerateData', 'BatchGenerate', 'MEMOptimizer', 'Detector', 'Analysis'):
            run([bundle/f'{name}.exe', '--gui-smoke', '--dimension', 2], timeout=45)
        run([bundle/'BLRWorkbench.exe', '--gui-flow', '--out', output/'gui-flow.json'], timeout=240)
    receipt = dict(version=version, status='PASS', platform=sys.platform, checks=checks,
                   gui='PASS' if gui else 'NOT_RUN', accelerators='JAX_CPU_JIT_AND_NUMBA' if accelerators else 'NOT_RUN',
                   developer_python_path_removed=True,
                   executable_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(), commands=records)
    (output/'validation.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--skip-gui', action='store_true')
    parser.add_argument('--skip-accelerators', action='store_true')
    args = parser.parse_args()
    print(json.dumps(validate(args.bundle, args.out, not args.skip_gui, not args.skip_accelerators), indent=2))
