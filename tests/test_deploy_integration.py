"""Opt-in real Compose recovery, using cached approved v1 on isolated loopback ports."""

from dataclasses import asdict
import json
import os
import socket
from uuid import uuid4

import pytest

from scripts import deploy_api

pytestmark = pytest.mark.skipif(os.environ.get('PHASE2_DOCKER_RECOVERY') != '1',
                                reason='Opt-in cached-image Compose recovery; never use the established project.')


@pytest.mark.parametrize('failure', ['prediction', 'occupied-port'])
def test_real_compose_restores_previous_healthy_configuration(tmp_path, monkeypatch, failure):
    project = 'p2-recovery-' + uuid4().hex[:12]
    monkeypatch.setattr(deploy_api, 'PROJECT_NAME', project)
    original_docker = deploy_api.docker
    def cached_docker(*args, **kwargs):
        if args[0] == 'pull':
            # Test cached digest only, never authenticate/download/change a registry.
            return original_docker('image', 'inspect', args[1], capture=True)
        return original_docker(*args, **kwargs)
    monkeypatch.setattr(deploy_api, 'docker', cached_docker)
    release = json.loads(deploy_api.DEFAULT_RELEASE_FILE.read_bytes())
    release_file = tmp_path / 'release.json'
    release_file.write_text(json.dumps(release))
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    assert port != 8001
    active = deploy_api.parse_deployment(release, port)
    state_dir = tmp_path / 'state'
    try:
        deploy_api.deploy(release_file, state_dir, port)
        before = (state_dir / 'state.json').read_bytes()
        if failure == 'prediction':
            release_file.write_text(json.dumps({**release, 'expected_minutes':999.0}))
            with pytest.raises(RuntimeError, match='previous release was restored'):
                deploy_api.deploy(release_file, state_dir, port)
        else:
            with socket.socket() as occupied:
                occupied.bind(('127.0.0.1', 0))
                occupied.listen()
                with pytest.raises(RuntimeError, match='previous release was restored'):
                    deploy_api.deploy(release_file, state_dir, occupied.getsockname()[1])
        assert (state_dir / 'state.json').read_bytes() == before
        assert deploy_api.read_state(state_dir / 'state.json')[0] == active
        deploy_api.smoke_api(f'http://127.0.0.1:{port}', active.expected_minutes, active.model_version)
        assert not (state_dir / '.deploy.lock').exists()
    finally:
        deploy_api.compose(active, 'down', '--timeout', '5', timeout=60)
