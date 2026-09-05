import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from m2a.video import read_frames,VideoFrames

class StreamingVideoTests(unittest.TestCase):
    def test_619_frames_are_streamed_completely_and_repeatably(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'619_frames.avi'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),24,(64,48))
            self.assertTrue(writer.isOpened())
            for f in range(619):writer.write(np.full((48,64,3),f%200,np.uint8))
            writer.release()
            frames,fps=read_frames(path,0,None,0)
            self.assertIsInstance(frames,VideoFrames)
            self.assertEqual(len(frames),619)
            self.assertEqual(fps,24)
            self.assertEqual(sum(1 for _ in frames),619)
            self.assertEqual(sum(1 for _ in frames),619)
            self.assertLess(abs(frames[-1].mean()-18),2)
            subset,_=read_frames(path,600,618,90)
            self.assertEqual(len(subset),19)
            self.assertEqual(subset[0].shape[:2],(64,48))
            self.assertEqual(sum(1 for _ in subset),19)

if __name__=='__main__':unittest.main()
