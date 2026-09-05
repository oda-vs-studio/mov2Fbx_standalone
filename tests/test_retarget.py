import subprocess
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from m2a.retarget import ROOT, load_skeleton, retarget_arrays, write_fbx
from m2a.export import PARENTS

@unittest.skipUnless((ROOT/'models/quinn_skeleton.txt').exists(),'User Quinn skeleton is not configured')
class RetargetTests(unittest.TestCase):
    def setUp(self):
        self.target=load_skeleton(ROOT/'models/quinn_skeleton.txt')
        joints=np.load(ROOT/'models/skeleton.npz')['joints']
        self.offsets=joints.copy()
        self.offsets[1:]-=joints[np.array(PARENTS[1:])]

    def test_motion_preserves_bone_lengths_and_ik_followers(self):
        rng=np.random.default_rng(512)
        rotations=Rotation.from_rotvec(rng.normal(size=(8*55,3))*.22).as_matrix().reshape(8,55,3,3)
        root=np.column_stack([np.linspace(0,.4,8),np.ones(8),np.linspace(0,.2,8)])
        t,r,w,report=retarget_arrays(rotations,root,self.offsets,self.target)
        self.assertLess(report['direction_max_error'],1e-8)
        for i,p in enumerate(self.target['parents']):
            name=self.target['names'][i]
            if p<0 or name=='pelvis' or name.startswith('ik_') or name=='center_of_mass':continue
            expected=np.linalg.norm(self.target['local_pos'][i])
            np.testing.assert_allclose(np.linalg.norm(w[:,i]-w[:,p],axis=1),expected,atol=1e-8)
        idx={n:i for i,n in enumerate(self.target['names'])}
        for helper,bone in [('ik_hand_l','hand_l'),('ik_hand_r','hand_r'),('ik_foot_l','foot_l'),('ik_foot_r','foot_r')]:
            np.testing.assert_allclose(w[:,idx[helper]],w[:,idx[bone]],atol=1e-8)
        self.assertAlmostEqual(np.linalg.norm(t[-1,0]-t[0,0]),np.linalg.norm([.4,0,.2])*report['translation_cm_per_m'],places=7)

    def test_reference_fbx_preserves_all_global_transforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            path=tmp/'reference.fbx'
            write_fbx(path,self.target,self.target['local_pos'][None],self.target['local_rot'][None],30,tmp)
            subprocess.run([str(ROOT/'bin/fbx_skeleton.exe'),str(path),str(tmp/'readback.txt')],check=True)
            actual=load_skeleton(tmp/'readback.txt')
            self.assertEqual(actual['names'],self.target['names'])
            np.testing.assert_array_equal(actual['parents'],self.target['parents'])
            np.testing.assert_allclose(actual['pos'],self.target['pos'],atol=1e-6)
            np.testing.assert_allclose(actual['rot'],self.target['rot'],atol=1e-7)

    def test_animation_fbx_sdk_roundtrip(self):
        rng=np.random.default_rng(85)
        r=Rotation.from_rotvec(rng.normal(size=(4*55,3))*.3).as_matrix().reshape(4,55,3,3)
        t,r,_,_=retarget_arrays(r,np.tile([0,1,0.],(4,1)),self.offsets,self.target)
        with tempfile.TemporaryDirectory() as tmp:
            write_fbx(Path(tmp)/'animated.fbx',self.target,t,r,29.97,tmp)

if __name__=='__main__':unittest.main()
