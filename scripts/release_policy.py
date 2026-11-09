"""Authorize main-only releases and verify pinned, approved bundle handoffs."""

import argparse
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APPROVALS = ROOT / 'deploy/release-approvals'


def model_version(value: str) -> int:
    if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
        raise ValueError('Supply a positive model version, using decimal digits only.')
    return int(value)


def authorize(event: str, ref: str, revision: str, main_revision: str, version: int) -> None:
    if not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (revision, main_revision)):
        raise ValueError('Release revisions must be full Git SHAs.')
    if event == 'workflow_dispatch':
        if ref != 'refs/heads/main' or revision != main_revision:
            raise ValueError('Manual releases must run on the current main revision.')
    elif event == 'push' and ref == 'refs/tags/phase2-image-v1' and version == 1:
        subprocess.run(['git', 'merge-base', '--is-ancestor', revision, main_revision], cwd=ROOT, check=True)
    else:
        raise ValueError('Unauthorized release trigger.')


def approval(version: int) -> dict:
    if type(version) is not int or version < 1:
        raise ValueError('Invalid release version.')
    path = APPROVALS / f'v{version}.json'
    if not path.is_file():
        raise ValueError('No checked-in approval record for this version; publication is blocked.')
    record = json.loads(path.read_bytes())
    if record['model_version'] != version or type(record['expected_minutes']) not in (int, float) or not isfinite(record['expected_minutes']) or record['expected_minutes'] <= 0:
        raise ValueError('Invalid approved model identity or smoke expectation.')
    if version == 1:
        from scripts.release_bundle import APPROVED_FILES
        if record['kind'] != 'frozen_v1' or record['files'] != {name: {'size': size, 'sha256': digest} for name, (size, digest) in APPROVED_FILES.items()}:
            raise ValueError('The frozen v1 anchors cannot be replaced.')
        if record['expected_minutes'] != 6.320402254818158:
            raise ValueError('The frozen v1 smoke expectation cannot be changed.')
        if set(record['historical_evidence_sha256']) != {'docs/results/phase2-v1/quality_report.json', 'docs/results/phase2-v1/registration.json'}:
            raise ValueError('Both frozen historical approval records are required.')
    elif (record['kind'] != 'provenance_v2' or type(record.get('artifact_run_id')) is not int
          or record['artifact_run_id'] <= 0 or record.get('artifact_name') != f'approved-model-v{version}'):
        raise ValueError('Future releases require a versioned approved artifact handoff.')
    if version != 1 and not re.fullmatch(r'[0-9a-f]{40}', record.get('source_revision', '')):
        raise ValueError('The approved producer needs an exact source revision.')
    names = {'manifest.json', 'model.joblib'}
    if version != 1:
        names |= {'environment.lock.txt', 'quality_report.json', 'run_report.json', 'registration.json', 'pytest.xml'}
    if set(record['files']) != names:
        raise ValueError('Approval omits required bundle/evidence files.')
    for identity in record['files'].values():
        if (type(identity['size']) is not int or not 0 < identity['size'] <= 10_000_000
                or not re.fullmatch(r'[0-9a-f]{64}', identity['sha256'])):
            raise ValueError('Every approved file needs a bounded size and SHA-256.')
    return record


def verify_handoff_run(record: dict, run: dict, main_revision: str) -> None:
    if (run.get('id') != record['artifact_run_id'] or run.get('conclusion') != 'success'
            or run.get('status') != 'completed' or run.get('head_branch') != 'main'
            or run.get('head_sha') != record['source_revision']
            or run.get('event') not in ('workflow_dispatch', 'push')
            or not isinstance(run.get('repository'), dict)
            or run['repository'].get('full_name') != 'vedanth-04/AI-Powered-Sustainable-Transportation-Advisor'):
        raise ValueError('The artifact producer is not the approved successful main run.')
    subprocess.run(['git', 'merge-base', '--is-ancestor', record['source_revision'], main_revision], cwd=ROOT, check=True)


def verify_bundle(directory: Path, record: dict) -> None:
    # Exact allowlist and hashes are checked before pickle deserialization.
    if {p.name for p in directory.iterdir()} != set(record['files']):
        raise ValueError('Unexpected or missing release files.')
    for name, identity in record['files'].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != identity['size'] or sha256(path.read_bytes()).hexdigest() != identity['sha256']:
            raise ValueError(f'Release file differs from its trusted approval: {name}')
    from src.api.bundle import load_bundle
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    if manifest['model_version'] != record['model_version']:
        raise ValueError('Manifest version differs from release selection.')
    if record['kind'] == 'provenance_v2':
        from src.models.check_quality import junit_counts, required_checks
        from src.models.provenance import SOURCES
        provenance = manifest.get('provenance', {})
        quality = json.loads((directory / 'quality_report.json').read_bytes())
        run = json.loads((directory / 'run_report.json').read_bytes())
        registration = json.loads((directory / 'registration.json').read_bytes())
        if (manifest.get('manifest_version') != 2 or provenance.get('release_eligible') is not True
                or provenance.get('source_worktree_dirty') is not False or provenance.get('data', {}).get('kind') != 'dvc'
                or quality.get('quality_gate_passed') is not True or quality.get('approval_schema_version') != 2
                or set(quality['checks']) != required_checks(quality['candidate']) or not all(v is True for v in quality['checks'].values())):
            raise ValueError('Research/synthetic/incomplete approvals are ineligible for publication.')
        for name, key in [('quality_report.json', 'quality_report_sha256'), ('run_report.json', 'run_report_sha256'), ('environment.lock.txt', 'dependency_lock_sha256')]:
            if provenance[key] != record['files'][name]['sha256']:
                raise ValueError('Manifest evidence hashes differ from the approved handoff.')
        if (quality['run_report_sha256'] != provenance['run_report_sha256']
                or quality['pytest_xml_sha256'] != record['files']['pytest.xml']['sha256']
                or quality['pytest'] != junit_counts(directory / 'pytest.xml')
                or quality['candidate_run_id'] != provenance['training_run_id']
                or run['mlflow_run_ids'][quality['candidate']] != provenance['training_run_id']
                or quality['data_identity'] != provenance['data']
                or run['traversals_sha256'] != provenance['data']['input_sha256']
                or quality['candidate_joblib_sha256'] != manifest['model_sha256']
                or registration['status'] != 'READY' or registration['version'] != manifest['model_version']
                or registration['training_run_id'] != provenance['training_run_id']
                or registration['joblib_sha256'] != manifest['model_sha256']
                or registration['quality_report_sha256'] != provenance['quality_report_sha256']
                or registration['verified_predictions'] != run['split_counts']['test']
                or provenance['source_git_sha'] != record['source_revision']
                or quality['git_head'] != provenance['source_git_sha']
                or quality['working_tree_source_sha256'] != provenance['source_sha256']
                or not set(SOURCES).issubset(provenance['source_sha256'])):
            raise ValueError('Approval, registry receipt, data and manifest identities differ.')
        for name, digest in provenance['source_sha256'].items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Release source differs from evaluated source.')
    else:
        for name, digest in record['historical_evidence_sha256'].items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Frozen historical v1 evidence changed.')
    load_bundle(directory, expected_manifest_sha256=record['files']['manifest.json']['sha256'])
    from scripts.reproduce_model_workflow import check_exported_api
    actual = check_exported_api(directory)['prediction']['duration_minutes']
    if abs(actual - record['expected_minutes']) > 1e-8:
        raise ValueError('Approved bundle does not reproduce the recorded smoke prediction.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('authorize', 'verify', 'producer'))
    parser.add_argument('--model-version', required=True)
    parser.add_argument('--bundle-dir', type=Path, default=ROOT / 'outputs/phase2_serving')
    parser.add_argument('--producer-json', type=Path)
    args = parser.parse_args()
    version = model_version(args.model_version)
    record = approval(version)
    main_sha = subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip()
    if args.command == 'authorize':
        authorize(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF'], os.environ['GITHUB_SHA'], main_sha, version)
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for name, value in [('version', version), ('expected_minutes', record['expected_minutes']),
                                ('artifact_run_id', record.get('artifact_run_id', '')),
                                ('artifact_name', record.get('artifact_name', ''))]:
                print(f'{name}={value}', file=stream)
    elif args.command == 'producer':
        verify_handoff_run(record, json.loads(args.producer_json.read_bytes()), main_sha)
    else:
        verify_bundle(args.bundle_dir, record)


if __name__ == '__main__':
    main()
