"""Reproducible, non-destructive Windows CUDA camera environment setup."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'da3': ('https://github.com/ByteDance-Seed/Depth-Anything-3.git', '3d835ec1a5802d64a8b8b15f817a1ab54809bfe4'),
    'geocalib': ('https://github.com/cvg/GeoCalib.git', '97b8968e7798a66bf04fcf791fb535624241bda7'),
}


def run(args, **kw):
    print('>', subprocess.list2cmdline(list(map(str, args))), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kw)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default='DA3-LARGE', choices=['DA3-LARGE', 'DA3-GIANT', 'DA3NESTED-GIANT-LARGE'])
    args = p.parse_args()
    if os.name != 'nt': raise RuntimeError('This setup targets Windows x64')
    bootstrap = ROOT/'.venv-camera-bootstrap/Scripts/python.exe'
    if not bootstrap.exists(): run([sys.executable, '-m', 'venv', bootstrap.parents[1]])
    run([bootstrap, '-m', 'pip', 'install', 'uv==0.12.10'])
    env = os.environ.copy()
    env['UV_PYTHON_INSTALL_DIR'] = str(ROOT/'runtime-camera/python')
    env['UV_CACHE_DIR'] = str(ROOT/'work/uv-cache')
    uv = bootstrap.with_name('uv.exe')
    python = ROOT/'.venv-camera/Scripts/python.exe'
    if not python.exists():
        run([uv, 'venv', '--python', '3.12', '--seed', ROOT/'.venv-camera'], env=env)
    run([python, '-c', 'import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8, "Use Python 3.12 x64; existing environment preserved"'])
    run([python, '-m', 'pip', 'install', 'torch==2.7.1+cu128', 'torchvision==0.22.1+cu128', '--index-url', 'https://download.pytorch.org/whl/cu128'])
    run([python, '-m', 'pip', 'install', '-r', ROOT/'requirements-camera.txt'])
    for name, (url, commit) in SOURCES.items():
        dest = ROOT/'third_party'/name
        if not dest.exists():
            run(['git', 'clone', url, dest])
            run(['git', '-C', dest, 'checkout', '--detach', commit])
        actual = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(dest), 'status', '--porcelain'], text=True).strip()
        if actual != commit or dirty:
            raise RuntimeError(f'{dest} differs from pinned clean source; existing files preserved')
        # Minimal inference dependencies are managed above. No xformers/gsplat/compiler required.
        run([python, '-m', 'pip', 'install', '--no-deps', dest])
    run([python, '-c', 'import torch; assert torch.cuda.is_available(); x=torch.randn(128,128,device="cuda"); y=x@x; torch.cuda.synchronize(); print(torch.__version__,torch.version.cuda,torch.cuda.get_device_name(0),float(y.norm()))'])
    run([python, '-m', 'tools.camera_worker', 'download', '--model', args.model])
    frozen = subprocess.check_output([str(python), '-m', 'pip', 'freeze'], text=True)
    (ROOT/'work/camera_environment.lock').write_text(frozen, encoding='utf-8')
    print('Camera setup complete. Use DropVideoToQuinnFBX_MovingCamera.bat.', flush=True)


if __name__ == '__main__': main()
