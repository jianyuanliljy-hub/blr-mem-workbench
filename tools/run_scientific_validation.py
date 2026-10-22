"""Freeze and run the 144-case protocol, keeping the complete solver log."""
import argparse
import contextlib
import json
from pathlib import Path

from blr_rm.benchmark import run_benchmark
from blr_rm.status import has_failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    log = args.out.with_suffix('.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('x', encoding='utf-8') as stream:
        with contextlib.redirect_stdout(stream):
            result = run_benchmark(args.out, 'validation')
    print(json.dumps({key: result[key] for key in ('planned', 'completed', 'execution_failures', 'groups')},
                     ensure_ascii=False, indent=2))
    return 2 if has_failures(result) else 0


if __name__ == '__main__':
    raise SystemExit(main())
