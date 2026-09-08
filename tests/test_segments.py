import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
from m2a import scene, drop_video


class SegmentTests(unittest.TestCase):
    def test_primary_selection_happens_after_all_actor_camera_masking(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';seen=[]
            tracks=[dict(id=i,valid=np.ones(24,dtype=bool),observed=np.ones(24,dtype=bool),
                boxes=np.tile([0.,0.,size,size],(24,1))) for i,size in [(1,40),(2,10)]]
            def worker(stage,folder,*args,**kwargs):
                if stage=='rectify':
                    folder.mkdir();(folder/'lens.json').write_text(json.dumps(dict(K=np.eye(3).tolist())))
                else:
                    self.assertFalse((out/'actor_selection.json').exists())
                    self.assertEqual(len(tracks),2)
                    (folder/'camera_report.json').write_text(json.dumps(dict(segments=[dict(id=1,start=0,end=24,camera_dir='.')],partial=False,input_frames=24,skipped_ranges=[],failures=[])))
            def solve_range(video,folder,models,provider,camera,selected,first,last,*args):
                seen.append(([t['id'] for t in selected],first,last))
                return dict(people_count=len(selected))
            with patch('m2a.moving_camera.worker',worker),patch('m2a.pipeline.read_frames',return_value=([None],24)),patch('m2a.tracking.detect_tracks',return_value=tracks),patch.object(scene,'solve_range',solve_range):
                report=scene.solve_auto('clip.mp4',out,Path(tmp),moving_camera=True,actor_mode='primary',log=lambda _:None)
            self.assertEqual(seen,[([1],0,24)])
            self.assertFalse(report['partial'])
            self.assertEqual(report['actor_selection']['excluded_track_ids'],[2])
            self.assertEqual(json.loads((out/'scene.json').read_text())['actor_selection']['selected_track_ids'],[1])

    def test_failed_middle_body_segment_does_not_hide_later_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';seen=[]
            def worker(stage,folder,*args,**kwargs):
                if stage=='rectify':
                    folder.mkdir()
                    (folder/'lens.json').write_text(json.dumps(dict(K=np.eye(3).tolist())))
                else:
                    entries=[dict(id=i+1,start=a,end=b,camera_dir=f'segments/{i+1:03d}') for i,(a,b) in enumerate([(0,24),(40,64),(80,104)])]
                    (folder/'camera_report.json').write_text(json.dumps(dict(segments=entries,partial=True,input_frames=120,skipped_ranges=[],failures=[])))
            def solve_range(video,folder,models,provider,camera,tracks,first,last,*args):
                seen.append((first,last))
                if first==40:raise ValueError('insufficient body scale evidence')
                return dict(people_count=2)
            with patch('m2a.moving_camera.worker',worker),patch('m2a.pipeline.read_frames',return_value=([None],24)),patch('m2a.tracking.detect_tracks',return_value=[]),patch.object(scene,'solve_range',solve_range):
                report=scene.solve_auto('clip.mp4',out,Path(tmp),moving_camera=True,log=lambda _:None)
            self.assertEqual(seen,[(0,24),(40,64),(80,104)])
            self.assertEqual([s['start'] for s in report['exports']],[0,80])
            self.assertEqual(report['segment_errors'][0]['start'],40)
            self.assertTrue((out/'segments/003/scene.json').exists())

    def test_drop_publishes_all_disjoint_ranges_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'models').mkdir();(root/'models/quinn_skeleton.txt').touch()
            video=root/'clip.mp4';video.touch()
            def solve(video,run,*args,**kwargs):
                run.mkdir(parents=True);entries=[]
                for i,(a,b) in enumerate([(0,24),(80,104)],1):
                    folder=run/f'segments/{i:03d}';folder.mkdir(parents=True)
                    (folder/'scene.fbx').write_bytes(str(a).encode())
                    (folder/'scene.json').write_text('{}')
                    entries.append(dict(directory=str(folder.relative_to(run)),start=a,end=b,people_count=1))
                result=dict(partial=True,exports=entries)
                (run/'segments_manifest.json').write_text(json.dumps(result))
                return result
            cap=Mock();cap.get.return_value=120
            with patch.object(drop_video,'ROOT',root),patch.object(drop_video,'solve_auto',solve),patch.object(drop_video.cv2,'VideoCapture',return_value=cap),patch('sys.argv',['drop',str(video),'--moving-camera']):
                self.assertEqual(drop_video.main(),0)
            self.assertEqual((root/'clip_frames_000080-000103_segment.fbx').read_bytes(),b'80')
            self.assertTrue((root/'clip_frames_000000-000023_segment.fbx').exists())
            self.assertEqual(len(json.loads((root/'clip_segments.json').read_text())['exports']),2)
            self.assertFalse(video.with_suffix('.fbx').exists())


if __name__=='__main__':unittest.main()
