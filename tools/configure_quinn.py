"""Extract the user-supplied FBX skeleton for engine-free subsequent exports."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import numpy as np
from m2a.retarget import ROOT, load_skeleton, write_fbx

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('fbx',type=Path)
    args=parser.parse_args()
    source=args.fbx.resolve()
    output=ROOT/'models/quinn_skeleton.txt'
    subprocess.run([str(ROOT/'bin/fbx_skeleton.exe'),str(source),str(output)],check=True)
    skeleton=load_skeleton(output)
    write_fbx(ROOT/'QuinnSkeleton.fbx',skeleton,skeleton['local_pos'][None],
              skeleton['local_rot'][None],30,ROOT/'work')
    (ROOT/'models/quinn_manifest.json').write_text(json.dumps(dict(source=str(source),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),bones=len(skeleton['names']),
        reference='FBX default transforms, converted to Maya Y-up and cm',
        mesh_included=False),indent=2),encoding='utf-8')

if __name__=='__main__': main()
