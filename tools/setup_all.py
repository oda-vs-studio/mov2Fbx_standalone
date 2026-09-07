"""Install body and moving-camera dependencies and models sequentially."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path)
    p.add_argument('--quinn',type=Path)
    p.add_argument('--noninteractive',action='store_true')
    p.add_argument('--camera-model',default='DA3-LARGE',choices=['DA3-LARGE','DA3-GIANT','DA3NESTED-GIANT-LARGE'])
    a=p.parse_args()
    body=[sys.executable,'-m','tools.bootstrap_setup']
    if a.engine:body+=['--engine',str(a.engine)]
    if a.quinn:body+=['--quinn',str(a.quinn)]
    if a.noninteractive:body+=['--noninteractive']
    subprocess.run(body,cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','tools.setup_camera','--model',a.camera_model],cwd=ROOT,check=True)
    print('Setup complete: body models, detection, Quinn FBX tools, GeoCalib and DA3. Use DropVideoToMovie2Anim.bat.',flush=True)


if __name__=='__main__':main()
