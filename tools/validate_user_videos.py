"""Reproducible full-clip verification for the seven supplied 24 fps videos."""
import json
import subprocess
import sys
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = Path(r'D:\Comfy-Desktop\ComfyUI-Shared\output\video')


def main():
    out = ROOT/'runs'/'user_validation'
    out.mkdir(parents=True,exist_ok=True)
    results = []
    # Explicit left/right ROIs, in 864x480 raster coordinates. No automatic identity claims.
    cases = [(16,None),(11,None),(14,None),(15,None),(25,([140,15,435,478],[430,15,710,478])),(23,([140,15,435,478],[430,15,740,478])),(24,([140,15,435,478],[430,15,710,478]))]
    for number,boxes in cases:
        run = out/f'{number:05d}'
        if (run/'SUCCESS').exists():
            results.append(dict(video=number,status='previous_success',output=str(run)))
            continue
        command = [sys.executable,'-u','-m','m2a','solve',str(VIDEOS/f'MiniMax_H3_{number:05d}_.mp4'),'--output',str(run),'--start','0','--end','123','--provider','dml']
        if boxes:
            command += ['--roi',*map(str,boxes[0]),'--roi2',*map(str,boxes[1])]
        print(f'BEGIN {number:05d} people={2 if boxes else 1}',flush=True)
        began=time.perf_counter()
        with (out/f'{number:05d}.log').open('w',encoding='utf-8') as log:
            process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        result=dict(video=number,status='success' if process.returncode==0 else 'failed',returncode=process.returncode,seconds=time.perf_counter()-began,output=str(run))
        results.append(result)
        (out/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(f'END {number:05d} {result["status"]} {result["seconds"]:.1f}s',flush=True)
    return int(any(r['status']=='failed' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
