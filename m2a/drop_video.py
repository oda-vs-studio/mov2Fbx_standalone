"""Video drag/drop entry point. One actor, full raster, complete video only."""
from pathlib import Path
from datetime import datetime
import argparse
import os
import sys
import traceback
import uuid
import cv2
from .retarget import ROOT, export_retarget
from .pipeline import solve


def main():
    parser=argparse.ArgumentParser(description='Drop videos: export Quinn skeleton animation beside each video')
    parser.add_argument('videos',type=Path,nargs='+')
    parser.add_argument('--provider',choices=['dml','cpu'],default='dml')
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
            if not 12<=frames<=600:
                raise ValueError(f'Video has {frames} frames. This version accepts 12..600; it never silently truncates.')
            if not (ROOT/'models/quinn_skeleton.txt').is_file(): raise FileNotFoundError('Quinn skeleton has not been configured')
            run=ROOT/'runs/drop'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
            print(f'\nInput: {video}\nOutput: {dest}\nWork: {run}',flush=True)
            solve(video,run,ROOT/'models',provider=args.provider,log=lambda s:print(s,flush=True))
            temp=run/'quinn.fbx'
            export_retarget(run,temp)
            # Exclusive creation avoids overwriting a file created during inference.
            import shutil
            created=False
            try:
                with dest.open('xb') as out, temp.open('rb') as src:
                    created=True
                    shutil.copyfileobj(src,out)
                    out.flush(); os.fsync(out.fileno())
            except BaseException:
                if created: dest.unlink(missing_ok=True)
                raise
            (run/'SUCCESS').write_text(str(dest),encoding='utf-8')
            print(f'OK: {dest}',flush=True)
        except Exception:
            failed=True
            error=traceback.format_exc()
            print(error,file=sys.stderr,flush=True)
            if run is not None and run.exists(): (run/'ERROR.txt').write_text(error,encoding='utf-8')
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
