import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess
from m2a import drop_video
from tools import setup_all


class PackagingTests(unittest.TestCase):
    def test_repeated_drop_creates_distinct_sibling_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'models').mkdir();(root/'models/quinn_skeleton.txt').touch()
            video=root/'a video.mp4';video.touch();runs=[]
            def solve(video,run,*args,**kwargs):
                run.mkdir(parents=True);runs.append(run)
                (run/'scene.fbx').write_bytes(b'fbx')
                return dict(people_count=1)
            cap=Mock();cap.get.return_value=16
            with patch.object(drop_video,'ROOT',root),patch.object(drop_video,'solve_auto',solve),patch.object(drop_video.cv2,'VideoCapture',return_value=cap),patch('sys.argv',['drop',str(video),'--moving-camera','--output-folder']):
                self.assertEqual(drop_video.main(),0)
                self.assertEqual(drop_video.main(),0)
            self.assertNotEqual(runs[0],runs[1])
            for run in runs:
                self.assertEqual(run.parent.parent,video.parent)
                self.assertEqual(run.name,'_work')
                self.assertEqual((run.parent/'scene.fbx').read_bytes(),b'fbx')

    def test_setup_stops_before_camera_if_body_setup_fails(self):
        with patch.object(setup_all.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'body')) as run,patch('sys.argv',['setup','--engine','D:/UE','--noninteractive']):
            with self.assertRaises(subprocess.CalledProcessError):setup_all.main()
        self.assertEqual(run.call_count,1)

    def test_setup_forwards_model_and_body_options_separately(self):
        with patch.object(setup_all.subprocess,'run') as run,patch('sys.argv',['setup','--engine','D:/UE','--camera-model','DA3-GIANT','--noninteractive']):
            setup_all.main()
        self.assertEqual(run.call_count,2)
        self.assertIn('--engine',run.call_args_list[0].args[0])
        self.assertEqual(run.call_args_list[1].args[0][-2:],['--model','DA3-GIANT'])


if __name__=='__main__':unittest.main()
