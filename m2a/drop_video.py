"""Video drag/drop entry point. Automatic one/two-person scene, complete video only."""
from pathlib import Path
from datetime import datetime
import argparse
import os
import sys
import traceback
import uuid
import cv2
from .retarget import ROOT, export_retarget
from .scene import solve_auto


def main():
    parser=argparse.ArgumentParser(description='Drop videos: export Quinn skeleton animation beside each video')
    parser.add_argument('videos',type=Path,nargs='+')
    parser.add_argument('--provider',choices=['dml','cpu'],default='dml')
    parser.add_argument('--no-tilt-correction',action='store_true',help='Keep camera-only orientation when the initial feet are not planted')
    args=parser.parse_args()
    failed=False
    for video in args.videos:
        run=None
        try:
            video=video.resolve()
            if not video.is_file() or video.suffix.lower() not in {'.mp4','.mov','.avi','.mkv','.webm','.m4v','.wmv'}:
                raise ValueError(f'Not a supported video: {video}')
            dest=video.with_suffix('.fbx')
            if dest.exists(): raise FileExistsError(f'FBX already exists; rename or remove it before retrying: {dest}')
            cap=cv2.VideoCapture(str(video)); frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
            if frames<12:
                raise ValueError(f'Video has {frames} frames. At least 12 frames are required.')
            if not (ROOT/'models/quinn_skeleton.txt').is_file(): raise FileNotFoundError('Quinn skeleton has not been configured')
            run=ROOT/'runs/drop'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
            print(f'\nInput: {video}\nOutput: {dest}\nWork: {run}',flush=True)
            report=solve_auto(video,run,ROOT/'models',provider=args.provider,correct_tilt=not args.no_tilt_correction,log=lambda s:print(s,flush=True))
            files=[(run/'scene.fbx',dest)]
            if report['people_count']>1:
                for i in range(1,report['people_count']+1):
                    files.append((run/f'person_{i:02d}'/'quinn.fbx',dest.with_name(dest.stem+f'_person_{i:02d}.fbx')))
            # Reserve all destinations before copying; preserve every existing output.
            import shutil
            created=[]
            try:
                for src,target in files:
                    with target.open('xb') as out:
                        created.append(target)
                        with src.open('rb') as inp: shutil.copyfileobj(inp,out)
                        out.flush(); os.fsync(out.fileno())
            except BaseException:
                for target in created: target.unlink(missing_ok=True)
                raise
            (run/'SUCCESS').write_text(str(dest),encoding='utf-8')
            for _,target in files: print(f'OK: {target}',flush=True)
        except Exception:
            failed=True
            error=traceback.format_exc()
            print(error,file=sys.stderr,flush=True)
            if run is not None and run.exists(): (run/'ERROR.txt').write_text(error,encoding='utf-8')
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
