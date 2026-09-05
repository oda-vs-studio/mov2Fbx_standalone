"""Read the known UE 5.8 SMPL-X float-array asset; fail closed on other layouts."""
import argparse
from pathlib import Path
import struct
import hashlib
import json
import numpy as np


def extract(engine, output):
    path = Path(engine)/'Engine/Plugins/Marketplace/MetaHumanBodyTracker_5.8/Content/SMPLX_NEUTRAL_2020_locked_head_array_f32.uasset'
    data = path.read_bytes()
    def array(count, name_id):
        needle = struct.pack('<i', count)
        found, index = [], 0
        while (index := data.find(needle,index)) >= 0:
            if index >= 37 and data[index-5:index-1] == struct.pack('<i',count*4+4) and data[index-37:index-33] == struct.pack('<i',name_id):
                found.append(index+4)
            index += 1
        if len(found) != 1:
            raise ValueError(f'Unsupported SMPL-X layout for property {name_id}: {found}')
        return np.frombuffer(data,dtype='<f4',count=count,offset=found[0])
    vertices = array(10475*3,10).reshape(10475,3,order='F')
    regressor = array(55*10475,5).reshape(55,10475,order='F')
    shapes = array(10475*3*886,1)[:10475*3*10].reshape(10475*3,10,order='F').reshape(10475,3,10)
    joints = regressor @ vertices
    deltas = np.einsum('jv,vck->jck',regressor,shapes)
    if not np.isfinite(joints).all() or not np.allclose(regressor.sum(axis=1),1,atol=.02):
        raise ValueError('Skeleton validation failed')
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/'skeleton.npz',joints=joints,shape_deltas=deltas)
    (output/'skeleton_manifest.json').write_text(json.dumps(dict(source=str(path),sha256=hashlib.sha256(data).hexdigest(),joints=55,shape_components=10),indent=2),encoding='utf-8')
    print('Extracted SMPL-X skeleton:',joints.shape,flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',default=r'D:\UE\UE_5.8')
    p.add_argument('--output',default='models')
    extract(**vars(p.parse_args()))
