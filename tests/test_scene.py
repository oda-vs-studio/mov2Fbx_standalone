import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from m2a.export import PARENTS,forward_kinematics
from m2a.retarget import ROOT,load_skeleton,retarget_arrays,write_fbx
from m2a.scene import stabilize_scene,source_soles,global_rotations,combine_targets,forward_target
from m2a.tracking import Tracker

class TrackingTests(unittest.TestCase):
    def test_crossing_people_keep_identity_with_appearance_and_velocity(self):
        tracker=Tracker(3)
        looks=np.eye(2)
        for f in range(30):
            boxes=np.array([[20+f*3,10,50+f*3,110],[140-f*3,10,170-f*3,110]],float)
            order=np.argsort(boxes[:,0])
            tracker.update(f,boxes[order],np.ones(2)*.9,looks[order])
        result=tracker.finish(30,(220,130))
        self.assertEqual(len(result),2)
        self.assertGreater(result[0]['boxes'][-1,0],result[1]['boxes'][-1,0])
        self.assertTrue(all(t['coverage']==1 for t in result))

    def test_long_absence_does_not_fabricate_motion(self):
        tracker=Tracker(3)
        for f in range(30):
            boxes=np.array([[10,0,60,100.]]) if f<15 else np.empty((0,4))
            tracker.update(f,boxes,np.ones(len(boxes))*.9,[np.array([1.,0])] if len(boxes) else [])
        with self.assertRaises(ValueError):tracker.finish(30,(100,120))


@unittest.skipUnless((ROOT/'models/quinn_skeleton.txt').exists(),'Quinn skeleton missing')
class SceneTests(unittest.TestCase):
    def actors(self):
        joints=np.load(ROOT/'models/skeleton.npz')['joints']
        offsets=joints.copy();offsets[1:]-=joints[np.array(PARENTS[1:])]
        tilt=Rotation.from_euler('xz',[13,-9],degrees=True).as_matrix()
        actors=[]
        for x in [-.8,.8]:
            local=np.tile(np.eye(3),(12,55,1,1))
            local[:,0]=tilt
            # A later forward bend must survive the constant initial calibration.
            local[8:,3]=Rotation.from_euler('x',25,degrees=True).as_matrix()
            root=np.tile(joints[0]+[x,0,3],(12,1))@tilt.T
            world=forward_kinematics(Rotation.from_matrix(local.reshape(-1,3,3)),root,offsets)
            actors.append(dict(local=local,root=root,world=world,offsets=offsets))
        return actors

    def test_initial_sole_tilt_removed_without_straightening_later_pose(self):
        actors=self.actors();before=copy.deepcopy(actors)
        report=stabilize_scene(actors,5)
        self.assertTrue(all(p['applied'] for p in report['people']))
        for a,b in zip(actors,before):
            self.assertLess(np.max(np.abs(a['soles'][:5,:,1])),1e-7)
            np.testing.assert_allclose(a['local'][:,1:],b['local'][:,1:],atol=1e-9)
            # Floor calibration removes pitch/roll but deliberately retains heading.
            np.testing.assert_allclose(a['local'][:5,0,:,1],np.tile([0,1,0],(5,1)),atol=1e-6)
        # A single shared origin preserves physical separation.
        self.assertAlmostEqual(np.linalg.norm(actors[0]['anchor']-actors[1]['anchor']),1.6,places=6)
        self.assertGreater(np.linalg.norm(actors[0]['root'][0]-actors[1]['root'][0]),1.5)

    def test_scene_common_scale_and_combined_fbx_roundtrip(self):
        actors=self.actors();stabilize_scene(actors,5)
        target=load_skeleton(ROOT/'models/quinn_skeleton.txt');animations=[]
        for a in actors:
            t,r,w,report=retarget_arrays(a['local'],a['root'],a['offsets'],target,translation_scale=100,floor_mode='none')
            self.assertEqual(report['translation_cm_per_m'],100)
            animations.append((t,r))
        combined,t,r=combine_targets(target,animations)
        self.assertEqual(len(combined['names']),179)
        self.assertEqual(len(set(combined['names'])),179)
        w,_=forward_target(t,r,combined['parents'])
        self.assertAlmostEqual(np.linalg.norm(w[0,1]-w[0,90]),160,places=5)
        with tempfile.TemporaryDirectory() as tmp:
            write_fbx(Path(tmp)/'pair.fbx',combined,t,r,24,tmp)

if __name__=='__main__':unittest.main()
