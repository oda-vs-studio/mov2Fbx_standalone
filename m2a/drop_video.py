"""Video drag/drop entry point. Automatic one/two-person scene, explicitly labelled partial moving-camera exports."""
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
    parser.add_argument('--moving-camera',action='store_true')
    parser.add_argument('--output-folder',action='store_true',help='Create a unique result folder beside each video, including intermediate work')
    parser.add_argument('--camera-model',default='DA3-LARGE',choices=['DA3-LARGE','DA3-GIANT','DA3NESTED-GIANT-LARGE'])
    args=parser.parse_args()
    failed=False
    for video in args.videos:
        run=None
        try:
            video=video.resolve()
            if not video.is_file() or video.suffix.lower() not in {'.mp4','.mov','.avi','.mkv','.webm','.m4v','.wmv'}:
                raise ValueError(f'Not a supported video: {video}')
            token=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
            result_dir=video.parent/(video.stem+'_Movie2Anim_'+token) if args.output_folder else video.parent
            dest=result_dir/(video.stem+'.fbx')
            if dest.exists() and not args.moving_camera: raise FileExistsError(f'FBX already exists; rename or remove it before retrying: {dest}')
            cap=cv2.VideoCapture(str(video)); frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
            if frames<12:
                raise ValueError(f'Video has {frames} frames. At least 12 frames are required.')
            if not (ROOT/'models/quinn_skeleton.txt').is_file(): raise FileNotFoundError('Quinn skeleton has not been configured')
            if args.output_folder:
                result_dir.mkdir()
                run=result_dir/'_work'
            else:
                run=ROOT/'runs/drop'/token
            print(f'\nInput: {video}\nOutput: {dest}\nWork: {run}',flush=True)
            report=solve_auto(video,run,ROOT/'models',provider=args.provider,correct_tilt=not args.no_tilt_correction,moving_camera=args.moving_camera,camera_model=args.camera_model,log=lambda s:print(s,flush=True))
            if 'exports' in report:
                files=[]
                for segment in report['exports']:
                    folder=run/segment['directory']
                    target=dest if not report['partial'] else dest.with_name(dest.stem+f"_frames_{segment['start']:06d}-{segment['end']-1:06d}_segment.fbx")
                    files.extend([(folder/'scene.fbx',target),(folder/'scene.json',target.with_suffix('.json'))])
                    if segment['people_count']>1:
                        for i in range(1,segment['people_count']+1):
                            files.append((folder/f'person_{i:02d}/quinn.fbx',target.with_name(target.stem+f'_person_{i:02d}.fbx')))
                report['output_files']=[target.name for _,target in files]
                (run/'segments_manifest.json').write_text(__import__('json').dumps(report,indent=2),encoding='utf-8')
                files.append((run/'segments_manifest.json',dest.with_name(dest.stem+'_segments.json')))
                print(f"Exporting {len(report['exports'])} verified segment(s); source ranges are in the manifest.",flush=True)
            else:
                if report.get('partial'):
                    dest=dest.with_name(dest.stem+f"_frames_{report['source_start_frame']:06d}-{report['source_end_frame_inclusive']:06d}_partial.fbx")
                    print(f"PARTIAL: source frames {report['source_start_frame']}..{report['source_end_frame_inclusive']} (zero-based). Remaining frames were not exported.",flush=True)
                files=[(run/'scene.fbx',dest)]
                if report.get('partial'):
                    files.append((run/'scene.json',dest.with_suffix('.json')))
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
            (run/('PARTIAL_SUCCESS' if report.get('partial') else 'SUCCESS')).write_text('\n'.join(str(target) for _,target in files),encoding='utf-8')
            for _,target in files: print(f'OK: {target}',flush=True)
        except Exception:
            failed=True
            error=traceback.format_exc()
            print(error,file=sys.stderr,flush=True)
            if run is not None and run.exists(): (run/'ERROR.txt').write_text(error,encoding='utf-8')
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
