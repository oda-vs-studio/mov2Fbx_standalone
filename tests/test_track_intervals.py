from pathlib import Path
import tempfile
import unittest
import numpy as np
from m2a.tracking import Tracker
from m2a.track_intervals import partition_tracks,prepare_intervals


class TrackIntervalTests(unittest.TestCase):
    def test_late_entry_and_long_absence_are_not_extrapolated(self):
        tracker=Tracker(max_gap=3)
        frames=list(range(10,30))+list(range(60,80))
        tracker.tracks=[dict(id=1,samples={i:(np.array([10.,10.,30.,70.]),.9) for i in frames})]
        tracks=tracker.finish_partial(100,(100,100))
        intervals,skips=partition_tracks(tracks,0,100)
        self.assertEqual([(s['start'],s['end']) for s in intervals],[(10,30),(60,80)])
        self.assertFalse(tracks[0]['valid'][40])
        self.assertTrue((tracks[0]['boxes'][40]==0).all())
        self.assertEqual(sum(s['end']-s['start'] for s in skips),60)

    def test_three_sequential_ids_are_accepted_but_simultaneous_three_are_skipped(self):
        tracks=[]
        for a,b in [(0,36),(24,60),(24,80)]:
            valid=np.zeros(80,dtype=bool);valid[a:b]=True
            tracks.append(dict(valid=valid))
        intervals,skips=partition_tracks(tracks,0,80)
        self.assertEqual([(i['start'],i['end'],i['track_indices']) for i in intervals],[(0,24,[0]),(36,60,[1,2]),(60,80,[2])])
        self.assertEqual((skips[0]['start'],skips[0]['end']),(24,36))

    def test_camera_slice_uses_source_offset_for_depth_and_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'depth').mkdir()
            pose=np.tile(np.c_[np.eye(3),np.zeros(3)],(50,1,1));pose[:,0,3]=np.arange(50)
            np.savez(root/'trajectory.npz',w2c=pose,frame_indices=np.arange(100,150),K=np.eye(3),size=[2,2],fps=24,up_world=[0,-1,0])
            for i in range(50):np.savez(root/'depth'/f'{i:06d}.npz',depth=np.full((2,2),i))
            valid=np.zeros(150,dtype=bool);valid[112:136]=True
            status=dict(partial=True,segments=[dict(id=1,start=100,end=150,camera_dir='.')])
            result,_=prepare_intervals(status,[dict(valid=valid)],root)
            folder=root/result['segments'][0]['camera_dir']
            camera=np.load(folder/'trajectory.npz')
            np.testing.assert_array_equal(camera['frame_indices'],np.arange(112,136))
            np.testing.assert_array_equal(camera['w2c'][:,0,3],np.arange(12,36))
            camera.close()
            self.assertEqual(np.load(folder/'depth/000000.npz')['depth'][0,0],12)


if __name__=='__main__':unittest.main()
