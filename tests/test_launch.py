import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from dual import launch


def test_cpu_launch_does_not_install_or_select_cuda(monkeypatch):
    monkeypatch.setenv('POCKET_TTS_DEVICE', 'cpu')
    install=Mock(side_effect=AssertionError('CPU must not install CUDA'))
    execute=Mock()
    monkeypatch.setattr(launch,'ensure_cuda_runtime',install)
    monkeypatch.setattr(launch.os,'execvpe',execute)
    launch.launch(['--port','8000'])
    assert not install.called
    assert execute.call_args.args[1][1:]==['-m','uvicorn','dual.main:app','--port','8000']


def test_cuda_launch_selects_runtime_before_app_import(monkeypatch):
    monkeypatch.setenv('POCKET_TTS_DEVICE','cuda:0')
    monkeypatch.setenv('POCKET_TTS_RUNTIME_CACHE','/models/runtime')
    install=Mock(return_value=Path('/models/runtime/ready'))
    validate=Mock();execute=Mock()
    monkeypatch.setattr(launch,'ensure_cuda_runtime',install)
    monkeypatch.setattr(launch,'validate_runtime',validate)
    monkeypatch.setattr(launch.os,'execvpe',execute)
    launch.launch([])
    install.assert_called_once_with('/models/runtime')
    validate.assert_called_once_with(Path('/models/runtime/ready'),require_gpu=True)
    assert execute.call_args.args[2]['PYTHONPATH'].split(':')[0]=='/models/runtime/ready'


def test_first_install_is_atomic_and_next_start_uses_cache(tmp_path,monkeypatch):
    install=Mock();validate=Mock()
    monkeypatch.setattr(launch.subprocess,'run',install)
    monkeypatch.setattr(launch,'validate_runtime',validate)
    target=launch.ensure_cuda_runtime(tmp_path)
    assert json.loads((target/'.runtime-complete.json').read_text())['torch']==launch.TORCH_VERSION
    assert 'torch=='+launch.TORCH_VERSION in install.call_args.args[0]
    assert launch.ensure_cuda_runtime(tmp_path)==target
    assert install.call_count==1
    assert not list(tmp_path.glob('*.install-*'))


def test_failed_install_is_not_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(launch.subprocess,'run',Mock(side_effect=RuntimeError('network failed')))
    with pytest.raises(RuntimeError,match='network failed'):
        launch.ensure_cuda_runtime(tmp_path)
    assert not (tmp_path/launch.runtime_key()).exists()
    assert not list(tmp_path.glob('*.install-*'))


def test_install_can_be_disabled(tmp_path,monkeypatch):
    monkeypatch.setenv('POCKET_TTS_AUTO_INSTALL_CUDA','false')
    with pytest.raises(RuntimeError,match='disabled'):
        launch.ensure_cuda_runtime(tmp_path)
