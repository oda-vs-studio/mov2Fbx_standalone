"""Interactive, repeatable Windows setup. Does not remove local models or runs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
MODEL_NAMES=['camera_calib','chmr_backbone','chmr_head','hue_step_simplified','hue_finalStep_simplified','ViTPose','ViTPosePost']
REQUIRED=[n+'.onnx' for n in MODEL_NAMES]+['OnnxExternalDataBytes','OnnxExternalDataDescriptor','skeleton.npz','manifest.json','skeleton_manifest.json']


def run(args,env=None):
    print('Running: '+subprocess.list2cmdline([str(a) for a in args]),flush=True)
    subprocess.run([str(a) for a in args],cwd=ROOT,env=env,check=True)


def pick(title,folder=True):
    import tkinter as tk
    from tkinter import filedialog
    window=tk.Tk();window.withdraw();window.attributes('-topmost',True)
    try:
        result=filedialog.askdirectory(title=title,parent=window) if folder else filedialog.askopenfilename(title=title,parent=window,filetypes=[('Quinn FBX','*.fbx')])
    finally:window.destroy()
    if not result:raise RuntimeError('Selection cancelled. Existing files were kept.')
    return Path(result)


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def vcvars():
    if os.environ.get('VS_VCVARS'):
        p=Path(os.environ['VS_VCVARS'])
        if p.is_file():return p
    where=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    if where.is_file():
        result=subprocess.run([str(where),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],capture_output=True,text=True,check=True)
        if result.stdout.strip():
            p=Path(result.stdout.strip())/'VC/Auxiliary/Build/vcvars64.bat'
            if p.is_file():return p
    raise RuntimeError('Install Visual Studio / Build Tools with Desktop development with C++ and a Windows SDK, or set VS_VCVARS.')


def check_engine(engine):
    engine=engine.resolve()
    if engine.name.lower()=='engine':engine=engine.parent
    plugin=engine/'Engine/Plugins/Marketplace/MetaHumanBodyTracker_5.8'
    required=[plugin/'Content/Models/Offline'/f'{n}.uasset' for n in MODEL_NAMES]
    required += [plugin/'Content/SMPLX_NEUTRAL_2020_locked_head_array_f32.uasset',
                 engine/'Engine/Source/ThirdParty/FBX/2020.2/include/fbxsdk.h',
                 engine/'Engine/Source/ThirdParty/FBX/2020.2/lib/vs2017/x64/release/libfbxsdk.lib',
                 engine/'Engine/Binaries/ThirdParty/FBX/2020.2/Win64/libfbxsdk.dll']
    missing=[str(p) for p in required if not p.is_file()]
    if missing:raise RuntimeError('Required UE 5.8 plugin or FBX SDK files are missing:\n'+'\n'.join(missing)+'\nSee README prerequisites. No existing models were changed.')
    return engine


def verify_models(directory):
    if not all((directory/n).is_file() for n in REQUIRED):return False
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    hashes={}
    for entry in manifest:
        for item in entry['files']:
            name=item['file']
            if Path(name).name!=name:raise ValueError('Invalid model manifest path')
            hashes[name]=item['sha256']
        hashes[Path(entry['asset']).stem+'.onnx']=entry['runtime_onnx_sha256']
    expected=set(REQUIRED)-{'skeleton.npz','manifest.json','skeleton_manifest.json'}
    if not expected.issubset(hashes):raise ValueError('Model manifest does not cover required runtime files')
    for name in sorted(expected):
        if digest(directory/name)!=hashes[name]:raise ValueError(f'Existing model checksum mismatch: {name}. Files were kept; use a fresh checkout or inspect the model before retrying.')
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path)
    p.add_argument('--quinn',type=Path,help='Exported SKM_Quinn_Simple FBX; existing configured skeleton is reused when omitted')
    p.add_argument('--noninteractive',action='store_true')
    p.add_argument('--check-only',action='store_true',help='Read-only prerequisite check; no install or extraction')
    args=p.parse_args()
    if sys.version_info[:2]!=(3,13) or struct.calcsize('P')!=8:
        raise RuntimeError('Python 3.13 64-bit is required. Install it from python.org, or set M2A_PYTHON to its python.exe.')
    engine=args.engine or (Path(os.environ['UE_ROOT']) if os.environ.get('UE_ROOT') else None)
    if engine is None:
        if args.noninteractive:raise ValueError('--engine is required in noninteractive mode')
        engine=pick('Select Unreal Engine 5.8 folder (contains Engine)')
    engine=check_engine(engine);compiler=vcvars()
    quinn=args.quinn
    configured=(ROOT/'models/quinn_skeleton.txt').is_file()
    if quinn is None and not configured:
        if args.noninteractive:raise ValueError('--quinn is required for a fresh setup; export SKM_Quinn_Simple to FBX first')
        quinn=pick('Select exported SKM_Quinn_Simple.FBX',folder=False)
    if quinn is not None and not quinn.is_file():raise FileNotFoundError(quinn)
    print(f'UE: {engine}\nC++ tools: {compiler}\nQuinn: {quinn or "reuse existing skeleton"}',flush=True)
    if args.check_only:
        print('Prerequisites OK. No files changed.');return
    env=os.environ.copy();env['UE_ROOT']=str(engine);env['VS_VCVARS']=str(compiler)
    env['PYTHONUTF8']='1'
    py=ROOT/'.venv/Scripts/python.exe'
    if not py.exists():run([sys.executable,'-m','venv',ROOT/'.venv'])
    run([py,'-c','import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize("P")==8, "Existing venv must use Python 3.13 x64"'])
    run([py,'-m','pip','install','-r',ROOT/'requirements.lock.txt'])
    (ROOT/'work').mkdir(exist_ok=True);models=ROOT/'models'
    if verify_models(models):print('Verified existing models; preserving them.',flush=True)
    else:
        staging=ROOT/'work'/('setup_models_'+uuid.uuid4().hex[:10])
        run([py,'-m','tools.extract_models','--engine',engine,'--output',staging],env)
        run([py,'-m','tools.extract_skeleton','--engine',engine,'--output',staging],env)
        if not verify_models(staging):raise RuntimeError('Extraction did not produce the complete model set')
        # Check every conflict before copying; never overwrite an existing model.
        for name in REQUIRED:
            if (models/name).exists() and digest(models/name)!=digest(staging/name):
                raise RuntimeError(f'Existing {name} differs. Original files and extraction in {staging} were preserved; use a fresh checkout to switch versions.')
        models.mkdir(exist_ok=True)
        for name in REQUIRED:
            if not (models/name).exists():shutil.copy2(staging/name,models/name)
        print(f'Extraction backup retained: {staging}',flush=True)
    for name in ['fbx','skeleton','retarget']:
        run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(ROOT/'tools'/f'build_{name}.bat')],env)
    run([py,'-m','tools.setup_detection'],env)
    if quinn is not None:
        if configured:
            backup=ROOT/'work'/('quinn_backup_'+uuid.uuid4().hex[:10]);backup.mkdir()
            for name in ['quinn_skeleton.txt','quinn_manifest.json']:
                if (models/name).exists():shutil.copy2(models/name,backup/name)
            if (ROOT/'QuinnSkeleton.fbx').exists():shutil.copy2(ROOT/'QuinnSkeleton.fbx',backup/'QuinnSkeleton.fbx')
        run([py,'-m','tools.configure_quinn',quinn],env)
    run([py,'-m','unittest','discover','-s','tests','-v'],env)
    run([py,'-m','m2a','doctor'],env)
    (ROOT/'work/setup_config.json').write_text(json.dumps(dict(engine=str(engine),vcvars=str(compiler),quinn=str(quinn) if quinn else 'existing',python=str(py)),indent=2),encoding='utf-8')
    print('Setup complete. Drop videos onto DropVideoToQuinnFBX.bat.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(f'\nSETUP FAILED: {error}',file=sys.stderr);sys.exit(1)
