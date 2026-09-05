"""Install the pinned official YOLOX-S detector; no torch or UE dependency."""
from pathlib import Path
import hashlib
import json
import urllib.request

URL='https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx'
SHA256='c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'

def main():
    root=Path(__file__).resolve().parents[1]
    target=root/'models/yolox_s.onnx';target.parent.mkdir(exist_ok=True)
    if not target.exists():
        partial=target.with_suffix('.onnx.part')
        print('Downloading official YOLOX-S ONNX',flush=True)
        urllib.request.urlretrieve(URL,partial)
        if hashlib.sha256(partial.read_bytes()).hexdigest()!=SHA256:raise ValueError('Detector SHA256 mismatch')
        partial.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    if digest!=SHA256:raise ValueError('Existing detector differs from the pinned official model')
    (target.parent/'yolox_manifest.json').write_text(json.dumps(dict(url=URL,sha256=digest,
        source='Megvii-BaseDetection/YOLOX official 0.1.1rc0 release',license='Apache-2.0',
        use='COCO person detection; custom appearance/motion tracker'),indent=2),encoding='utf-8')
    print('Person detector ready',flush=True)

if __name__=='__main__':main()
