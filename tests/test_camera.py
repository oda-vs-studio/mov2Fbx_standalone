import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from m2a.camera_math import similarity,align_poses,transform_body,validate_poses,unproject


class CameraTests(unittest.TestCase):
    def test_static_world_actor_survives_translating_rotating_camera(self):
        n=20
        r=Rotation.from_euler('y',np.linspace(-.2,.3,n)[:,None]).as_matrix()
        centers=np.column_stack([np.linspace(0,2,n),np.zeros(n),np.linspace(0,.2,n)])
        t=-np.einsum('fij,fj->fi',r,centers)
        ext=np.concatenate([r,t[:,:,None]],axis=2)
        world=np.array([.7,1.,5.])
        root=np.einsum('fij,j->fi',r,world)+t
        local=np.tile(np.eye(3),(n,55,1,1));local[:,0]=r
        out,positions=transform_body(local,root,ext,1.,np.eye(3))
        np.testing.assert_allclose(positions,np.tile(world,(n,1)),atol=1e-10)
        np.testing.assert_allclose(out[:,0],np.tile(np.eye(3),(n,1,1)),atol=1e-10)
        np.testing.assert_array_equal(out[:,1:],local[:,1:])

    def test_two_people_keep_distance_and_common_camera_scale(self):
        n=8;r=np.tile(np.eye(3),(n,1,1));t=np.zeros((n,3));t[:,0]=-np.arange(n)*.1
        ext=np.concatenate([r,t[:,:,None]],axis=2);local=np.tile(np.eye(3),(n,55,1,1))
        a=np.tile([1.,1.,4.],(n,1))+2*t
        b=a+np.array([2.,0.,1.])
        _,wa=transform_body(local,a,ext,2.,np.eye(3));_,wb=transform_body(local,b,ext,2.,np.eye(3))
        np.testing.assert_allclose(wa,np.tile([1.,1.,4.],(n,1)),atol=1e-10)
        np.testing.assert_allclose(wb-wa,np.tile([2.,0.,1.],(n,1)),atol=1e-10)

    def test_similarity_and_pose_alignment_preserve_projection(self):
        x=np.random.default_rng(1).normal(size=(100,3));r=Rotation.from_euler('xyz',[.1,.3,-.2]).as_matrix()
        y=2.4*x@r.T+[1,2,3];s,q,t=similarity(x,y)
        np.testing.assert_allclose(s*x@q.T+t,y,atol=1e-10)
        ext=np.array([np.column_stack([np.eye(3),[0,0,8.]])])
        adjusted=align_poses(ext,s,q,t)[0]
        before=x+ext[0,:,3];after=y@adjusted[:,:3].T+adjusted[:,3]
        np.testing.assert_allclose(before[:,:2]/before[:,2:],after[:,:2]/after[:,2:],atol=1e-10)

    def test_invalid_pose_rejected(self):
        with self.assertRaises(ValueError):validate_poses(np.zeros((4,3,4)))
        with self.assertRaises(ValueError):validate_poses(np.full((4,3,4),np.nan))

    def test_unprojection_known_camera(self):
        k=np.array([[100,0,50],[0,100,50],[0,0,1.]])
        np.testing.assert_allclose(unproject([2,4],k,[[50,50],[75,25]]),[[0,0,2],[1,-1,4]])



class CameraSeamTests(unittest.TestCase):
    def test_overlap_anchor_preserves_pose_despite_different_window_scale(self):
        from m2a.camera_math import anchor_similarity
        old=np.column_stack([Rotation.from_euler('xyz',[.2,-.4,.1]).as_matrix(),[2.,1.,-3.]])
        new=np.column_stack([Rotation.from_euler('xyz',[-.3,.1,-.5]).as_matrix(),[-1.,.5,2.]])
        q,t=anchor_similarity(old,new,1.7)
        out=align_poses(new[None],1.7,q,t)[0]
        np.testing.assert_allclose(out,old,atol=1e-10)

    def test_network_roundoff_projects_to_proper_rotation(self):
        pose=np.column_stack([np.eye(3),[1.,2.,3.]])[None]
        pose[0,0,1]=1e-4
        clean=validate_poses(pose)
        np.testing.assert_allclose(clean[0,:,:3]@clean[0,:,:3].T,np.eye(3),atol=1e-12)
        np.testing.assert_array_equal(clean[:,:,3],pose[:,:,3])


class FragmentTests(unittest.TestCase):
    def track(self,id,start,end,x=10,look=None):
        return dict(id=id,samples={f:(np.array([x,10,x+40,110.]),.9) for f in range(start,end)},
                    appearance=np.array([1.,0.]) if look is None else np.array(look))

    def test_short_nonoverlapping_gap_rejoins_actor(self):
        from m2a.tracking import Tracker
        t=Tracker(10);t.tracks=[self.track(1,0,50),self.track(2,53,100,x=30)]
        joined=t.stitch_fragments()
        self.assertEqual(len(joined),1)
        self.assertEqual(len(t.finish(100,(200,150))),1)

    def test_overlapping_people_and_different_appearance_do_not_merge(self):
        from m2a.tracking import Tracker
        t=Tracker(10);t.tracks=[self.track(1,0,60),self.track(2,50,100)]
        self.assertEqual(t.stitch_fragments(),[])
        t.tracks=[self.track(1,0,50),self.track(2,53,100,look=[0.,1.])]
        self.assertEqual(t.stitch_fragments(),[])

    def test_ambiguous_predecessors_do_not_merge(self):
        from m2a.tracking import Tracker
        t=Tracker(10);t.tracks=[self.track(1,0,50),self.track(2,0,50,x=20),self.track(3,53,100)]
        self.assertEqual(t.stitch_fragments(),[])
