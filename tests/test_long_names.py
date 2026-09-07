import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from m2a import drop_video


class LongNameTests(unittest.TestCase):
    def test_long_japanese_and_emoji_name_is_not_repeated_in_fbx_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'models').mkdir();(root/'models/quinn_skeleton.txt').touch()
            video=root/(('ジャンボリーミッキー😊'*8)+'.mp4');video.touch()
            runs=[]
            def solve(video,run,*args,**kwargs):
                runs.append(run);run.mkdir(parents=True)
                (run/'scene.fbx').write_bytes(b'scene');(run/'scene.json').write_text('{}')
                for i in [1,2]:
                    (run/f'person_{i:02d}').mkdir()
                    (run/f'person_{i:02d}/quinn.fbx').write_bytes(b'actor')
                report=dict(partial=True,exports=[dict(directory='.',start=834,end=846,people_count=2)])
                (run/'segments_manifest.json').write_text(json.dumps(report))
                return report
            cap=Mock();cap.get.return_value=1000
            with patch('builtins.print'),patch.object(drop_video,'ROOT',root),patch.object(drop_video,'solve_auto',solve),patch.object(drop_video.cv2,'VideoCapture',return_value=cap),patch('sys.argv',['drop',str(video),'--moving-camera','--output-folder']):
                self.assertEqual(drop_video.main(),0)
            folder=runs[0].parent
            self.assertEqual(json.loads((folder/'input.json').read_text(encoding='utf-8'))['video'],str(video))
            self.assertEqual((folder/'scene_frames_000834-000845_segment_person_02.fbx').read_bytes(),b'actor')
            self.assertTrue(all(len(str(p).encode('utf-16-le'))//2<250 for p in folder.glob('*.fbx')))


if __name__=='__main__':unittest.main()
