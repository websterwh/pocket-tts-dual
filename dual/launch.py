"""Select CPU or a cached CUDA runtime before importing the application."""
import fcntl
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

_LOG = logging.getLogger(__name__)
TORCH_VERSION = '2.13.0+cu126'
CUDA_VERSION = '12.6'
TORCH_INDEX = 'https://download.pytorch.org/whl/cu126'


def runtime_key():
    return f'torch-{TORCH_VERSION}-py{sys.version_info.major}{sys.version_info.minor}-{platform.machine()}'


def runtime_env(directory):
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(directory), env.get('PYTHONPATH', '')]))
    return env


def validate_runtime(directory, require_gpu=False):
    code = (
        'import torch; '
        f'assert torch.__version__ == {TORCH_VERSION!r}, torch.__version__; '
        f'assert torch.version.cuda == {CUDA_VERSION!r}, torch.version.cuda; '
    )
    if require_gpu:
        code += (
            'assert torch.cuda.is_available(), "CUDA is unavailable: check GPU attachment and host driver"; '
            'print("CUDA runtime ready:", torch.cuda.get_device_name(0), flush=True)'
        )
    subprocess.run([sys.executable, '-c', code], env=runtime_env(directory), check=True)


def ensure_cuda_runtime(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / runtime_key()
    # Multiple containers may share /models. Install once and publish atomically.
    with (root / (runtime_key() + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = target / '.runtime-complete.json'
        if marker.is_file():
            try:
                manifest = json.loads(marker.read_text())
                if manifest.get('torch') == TORCH_VERSION:
                    validate_runtime(target)
                    return target
            except (ValueError, subprocess.CalledProcessError):
                _LOG.warning('Cached CUDA runtime needs repair')
        if os.environ.get('POCKET_TTS_AUTO_INSTALL_CUDA', 'true').lower() in {'false', '0', 'no'}:
            raise RuntimeError('CUDA runtime is not cached and POCKET_TTS_AUTO_INSTALL_CUDA is disabled')
        staging = Path(tempfile.mkdtemp(prefix=runtime_key() + '.install-', dir=root))
        try:
            _LOG.info('Installing CUDA %s PyTorch into %s; first startup downloads several GB', CUDA_VERSION, root)
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '--only-binary=:all:',
                '--target', str(staging), '--index-url', TORCH_INDEX, 'torch==' + TORCH_VERSION,
            ], check=True)
            validate_runtime(staging)
            (staging / '.runtime-complete.json').write_text(json.dumps({
                'torch': TORCH_VERSION, 'cuda': CUDA_VERSION,
            }))
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
            return target
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def launch(args=None):
    args = sys.argv[1:] if args is None else args
    device = os.environ.get('POCKET_TTS_DEVICE', 'cpu').lower()
    env = os.environ.copy()
    if device == 'cuda' or device.startswith('cuda:'):
        root = os.environ.get('POCKET_TTS_RUNTIME_CACHE', '/models/.pocket-tts-runtime')
        runtime = ensure_cuda_runtime(root)
        validate_runtime(runtime, require_gpu=True)
        env = runtime_env(runtime)
    os.execvpe(sys.executable, [sys.executable, '-m', 'uvicorn', 'dual.main:app', *args], env)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    launch()
