"""Release authorization and evidence checks, without publishing or registry access."""

from hashlib import sha256
import json
from pathlib import Path

import pytest
import yaml
from tests.test_api import model_bundle

from scripts import release_policy as policy


@pytest.mark.parametrize('value', ['0', '-1', '1; echo unsafe', '../1', '01', '1\n', '', '1.0'])
def test_version_input_cannot_be_used_as_shell_or_path(value):
    with pytest.raises(ValueError):
        policy.model_version(value)


@pytest.mark.parametrize('event,ref,sha', [('workflow_dispatch', 'refs/heads/feature', 'a'*40), ('workflow_dispatch', 'refs/heads/main', 'b'*40), ('pull_request', 'refs/heads/main', 'a'*40), ('push', 'refs/tags/other', 'a'*40)])
def test_unauthorized_contexts_fail(event, ref, sha):
    with pytest.raises(ValueError):
        policy.authorize(event, ref, sha, 'a'*40, 1)


def test_main_and_legacy_tag_authorization(monkeypatch):
    policy.authorize('workflow_dispatch', 'refs/heads/main', 'a'*40, 'a'*40, 1)
    calls = []
    monkeypatch.setattr(policy.subprocess, 'run', lambda args, **kw: calls.append(args))
    policy.authorize('push', 'refs/tags/phase2-image-v1', 'b'*40, 'a'*40, 1)
    assert calls[0] == ['git', 'merge-base', '--is-ancestor', 'b'*40, 'a'*40]


def test_only_real_frozen_approval_is_shipped():
    record = policy.approval(1)
    assert record['kind'] == 'frozen_v1'
    for name, digest in record['historical_evidence_sha256'].items():
        data = (policy.ROOT / name).read_bytes().replace(b'\r\n',b'\n')
        assert sha256(data).hexdigest() == digest
        assert sha256(data.replace(b'\n',b'\r\n').replace(b'\r\n',b'\n')).hexdigest() == digest
    with pytest.raises(ValueError, match='No checked-in approval'):
        policy.approval(2)


def test_frozen_anchors_cannot_be_replaced(tmp_path, monkeypatch):
    record = policy.approval(1)
    record['files']['model.joblib']['sha256'] = '0'*64
    (tmp_path / 'v1.json').write_text(json.dumps(record))
    monkeypatch.setattr(policy, 'APPROVALS', tmp_path)
    with pytest.raises(ValueError, match='anchors'):
        policy.approval(1)


@pytest.mark.parametrize('change', ['conclusion', 'head_branch', 'head_sha', 'event', 'repository'])
def test_artifact_producer_identity_is_checked(monkeypatch, change):
    record = {'artifact_run_id': 123, 'source_revision': 'a'*40}
    run = {'id':123, 'conclusion':'success', 'status':'completed', 'head_branch':'main',
           'head_sha':'a'*40, 'event':'workflow_dispatch',
           'repository': {'full_name':'vedanth-04/AI-Powered-Sustainable-Transportation-Advisor'}}
    monkeypatch.setattr(policy.subprocess, 'run', lambda *a, **kw: None)
    policy.verify_handoff_run(record, run, 'b'*40)
    run[change] = 'untrusted'
    with pytest.raises(ValueError):
        policy.verify_handoff_run(record, run, 'b'*40)


def test_wrong_bundle_fails_before_loading(tmp_path, monkeypatch):
    from src.api import bundle
    monkeypatch.setattr(bundle, 'load_bundle', lambda *a, **kw: pytest.fail('Untrusted bytes reached the loader'))
    record = policy.approval(1)
    for name in record['files']:
        (tmp_path / name).write_bytes(b'synthetic is not approved')
    with pytest.raises(ValueError, match='trusted approval'):
        policy.verify_bundle(tmp_path, record)


def test_workflow_authorizes_and_verifies_before_publish():
    workflow = yaml.safe_load((policy.ROOT / '.github/workflows/release.yml').read_text())
    triggers = workflow.get('on', workflow.get(True))
    assert triggers['workflow_dispatch']['inputs']['model_version']['required']
    assert triggers['push']['tags'] == ['phase2-image-v1']
    steps = workflow['jobs']['build-and-publish']['steps']
    commands = '\n'.join(step.get('run','') for step in steps)
    assert commands.index('release_policy authorize') < commands.index('release_bundle stage')
    assert commands.index('release_policy producer') < commands.index('gh run download')
    assert commands.index('release_policy verify') < commands.index('docker build') < commands.index('docker push')
    assert commands.index('release_policy verify') < commands.index('release_policy registry') < commands.index('docker build')
    registry_step = next(step for step in steps if 'release_policy registry' in step.get('run',''))
    assert registry_step['if'] == "steps.policy.outputs.version != '1'"
    assert 'MLFLOW_TRACKING_TOKEN' in registry_step['env']
    assert 'MLFLOW_TRACKING_TOKEN' not in workflow['jobs']['build-and-publish'].get('env',{})
    assert 'sha-$GITHUB_SHA-v$MODEL_VERSION' in commands
    ci = yaml.safe_load((policy.ROOT / '.github/workflows/ci.yml').read_text())
    assert all(job.get('permissions', {}).get('packages') != 'write' for job in ci['jobs'].values())


def test_mock_v2_handoff_and_research_tampering(model_bundle):
    """Mock receipts validate the gate; never add this fixture to the real catalog."""
    from src.api.bundle import feature_schema_sha256
    from src.models.check_quality import required_checks
    from src.models.provenance import SOURCES, environment_identity
    directory, _ = model_bundle
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    manifest.update(manifest_version=2, model_version=2)
    candidate = 'Gradient Boosting Regressor'
    run_id = 'a'*32
    environment = environment_identity()
    lock = (policy.ROOT / 'requirements-dev.lock.txt').read_bytes()
    (directory / 'environment.lock.txt').write_bytes(lock)
    junit = b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="mock"/></testsuite>'
    (directory / 'pytest.xml').write_bytes(junit)
    data = {'kind':'dvc', 'input_sha256':'a'*64, 'raw_dvc_md5':'a'*32,
            **{k:'b'*64 for k in ('raw_sha256','pointer_sha256','lineage_sha256','dvc_lock_sha256')}}
    sources = {name:sha256((policy.ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    run = {'mlflow_run_ids':{candidate:run_id}, 'traversals_sha256':data['input_sha256'], 'split_counts':{'test':2}}
    (directory / 'run_report.json').write_text(json.dumps(run))
    run_hash = sha256((directory / 'run_report.json').read_bytes()).hexdigest()
    quality = {'approval_schema_version':2, 'quality_gate_passed':True, 'candidate':candidate,
               'checks':{name:True for name in required_checks(candidate)}, 'run_report_sha256':run_hash,
               'pytest_xml_sha256':sha256(junit).hexdigest(), 'pytest':{'tests':1,'failures':0,'errors':0,'skipped':0},
               'candidate_run_id':run_id, 'data_identity':data, 'candidate_joblib_sha256':manifest['model_sha256'],
               'git_head':'a'*40, 'working_tree_source_sha256':sources}
    (directory / 'quality_report.json').write_text(json.dumps(quality))
    quality_hash = sha256((directory / 'quality_report.json').read_bytes()).hexdigest()
    registration = {'status':'READY', 'version':2, 'training_run_id':run_id, 'joblib_sha256':manifest['model_sha256'],
                    'quality_report_sha256':quality_hash,'verified_predictions':2}
    (directory / 'registration.json').write_text(json.dumps(registration))
    manifest['provenance'] = {'training_run_id':run_id,'source_git_sha':'a'*40,'source_worktree_dirty':False,
                              'source_sha256':sources,'data':data,'feature_schema_sha256':feature_schema_sha256(),
                              'dependency_lock_sha256':environment['dependency_lock_sha256'],
                              'quality_report_sha256':quality_hash,'run_report_sha256':run_hash,
                              'model_runtime':environment['model_runtime'],'release_eligible':True}
    def receipt():
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        return {'kind':'provenance_v2','model_version':2,'expected_minutes':13.,'source_revision':'a'*40,
                'files':{p.name:{'size':p.stat().st_size,'sha256':sha256(p.read_bytes()).hexdigest()} for p in directory.iterdir()}}
    policy.verify_bundle(directory, receipt())
    manifest['provenance']['release_eligible'] = False
    with pytest.raises(ValueError, match='ineligible'):
        policy.verify_bundle(directory, receipt())
    manifest['provenance']['release_eligible'] = True
    manifest['provenance']['quality_report_sha256'] = '0'*64
    with pytest.raises(ValueError, match='hashes'):
        policy.verify_bundle(directory, receipt())


@pytest.mark.parametrize('failure', [None, 'revoked', 'artifact', 'connection', 'version'])
def test_shared_registry_gate_with_mock_responses(tmp_path, failure):
    from types import SimpleNamespace as NS
    model = tmp_path / 'remote.joblib'
    model.write_bytes(b'opaque fixture bytes, never deserialized')
    digest = sha256(model.read_bytes()).hexdigest()
    provenance = {'release_eligible':True,'training_run_id':'a'*32,'data':{'input_sha256':'b'*64},
                  **{key:'c'*64 for key in ('quality_report_sha256','run_report_sha256','dependency_lock_sha256')}}
    manifest = {'model_name':'BusTravelTimePredictor','model_version':2,'model_sha256':digest,
                'history_policy':'cold_start_v1','route_id':'90','segment_id':'demo','provenance':provenance}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    tags = {'quality_gate':'passed_historical_demo','joblib_sha256':digest,
            **{key:provenance[key] for key in ('quality_report_sha256','run_report_sha256','dependency_lock_sha256')},
            'demo_route':'90','demo_segment':'demo'}
    if failure == 'revoked':tags['quality_gate']='revoked'
    if failure == 'artifact':model.write_bytes(b'corrupt remote bytes')
    def factory(**kwargs):
        assert kwargs=={'tracking_uri':'https://tracking.example.test','registry_uri':'https://registry.example.test'}
        if failure == 'connection':raise RuntimeError('credential=never-expose-this')
        return NS(get_model_version=lambda *a:NS(name='BusTravelTimePredictor',version='3' if failure=='version' else '2',status='READY',run_id='a'*32,tags=tags),
                  get_run=lambda *a:NS(info=NS(status='FINISHED',lifecycle_stage='active'),data=NS(params={'history_policy':'cold_start_v1','traversals_sha256':'b'*64})),
                  download_artifacts=lambda *a:str(model))
    if failure:
        with pytest.raises(ValueError, match='publication is blocked') as error:
            policy.verify_registry(tmp_path,'https://tracking.example.test','https://registry.example.test',client_factory=factory)
        assert 'never-expose-this' not in str(error.value)
    else:
        policy.verify_registry(tmp_path,'https://tracking.example.test','https://registry.example.test',client_factory=factory)


@pytest.mark.parametrize('uri',['', 'http://registry.test','https://user:password@registry.test','https://registry.test?token=hidden'])
def test_shared_registry_requires_explicit_safe_endpoints(tmp_path, uri):
    with pytest.raises(ValueError,match='HTTPS'):
        policy.verify_registry(tmp_path,uri,uri)
