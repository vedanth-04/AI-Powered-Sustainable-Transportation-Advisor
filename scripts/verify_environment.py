"""Check CPython 3.12 and every active pin without importing training packages."""

import argparse
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, distribution
import json
from pathlib import Path
import platform
import sys

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def verify(lock: Path, *, require_venv: bool = False) -> dict:
    errors = []
    if sys.version_info[:2] != (3, 12) or platform.python_implementation() != 'CPython':
        errors.append('Use CPython 3.12.')
    if require_venv and sys.prefix == sys.base_prefix:
        errors.append('Use a new isolated virtual environment.')
    packages = {}
    for line in lock.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        pins = list(req.specifier)
        if len(pins) != 1 or pins[0].operator != '==' or '*' in pins[0].version or req.url:
            raise ValueError(f'Expected one exact package pin: {req.name}')
        try:
            dist = distribution(req.name)
            packages[req.name] = dist.version
            if dist.version not in req.specifier:
                errors.append(f'{req.name}: expected {req.specifier}, installed {dist.version}.')
            if require_venv and not Path(dist.locate_file('')).resolve().is_relative_to(Path(sys.prefix).resolve()):
                errors.append(f'{req.name}: comes from outside the isolated environment.')
        except PackageNotFoundError:
            errors.append(f'{req.name}: not installed.')
    return {'python': platform.python_version(), 'platform': sys.platform,
            'lock_sha256': sha256(lock.read_bytes()).hexdigest(),
            'packages': packages, 'errors': errors, 'passed': not errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'requirements-dev.lock.txt')
    parser.add_argument('--require-venv', action='store_true')
    args = parser.parse_args()
    result = verify(args.lock, require_venv=args.require_venv)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
