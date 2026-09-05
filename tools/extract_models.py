"""Extract uncooked UE 5.8 NNE FileData and AdditionalFileData, without UE."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct


def resolve_external_data(destination):
    import onnx
    descriptor = destination / 'OnnxExternalDataDescriptor'
    if not descriptor.exists():
        return
    data = descriptor.read_bytes()
    count = struct.unpack_from('<i', data, 0)[0]
    cursor, offset, locations = 4, 0, {}
    for _ in range(count):
        length = struct.unpack_from('<i', data, cursor)[0]
        cursor += 4
        if not 0 < length < 4096:
            raise ValueError('Unsupported ONNX external descriptor')
        name = data[cursor:cursor+length].decode('utf-8').rstrip('\0')
        cursor += length
        size = struct.unpack_from('<q', data, cursor)[0]
        cursor += 8
        locations[name] = (offset, size)
        offset += size
    if cursor != len(data) or offset != (destination/'OnnxExternalDataBytes').stat().st_size:
        raise ValueError('External descriptor size mismatch')
    path = destination/'ViTPose.onnx'
    model = onnx.load(str(path), load_external_data=False)
    for tensor in model.graph.initializer:
        if tensor.data_location == onnx.TensorProto.EXTERNAL:
            info = {entry.key:entry.value for entry in tensor.external_data}
            key = info['location']
            if key == 'OnnxExternalDataBytes':
                continue
            start, size = locations[key]
            tensor.ClearField('external_data')
            for key, value in dict(location='OnnxExternalDataBytes', offset=str(start), length=str(size)).items():
                entry = tensor.external_data.add()
                entry.key, entry.value = key, value
    onnx.save(model, str(path))


def extract(asset, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with asset.open('rb') as src:
        header = src.read(65536)
        marker = b'\x05\x00\x00\x00onnx\x00'
        positions = [i for i in range(len(header)) if header.startswith(marker, i)]
        candidates = []
        for pos in positions:
            start = pos + len(marker) + 8
            size = struct.unpack_from('<q', header, start - 8)[0]
            if 0 < size <= asset.stat().st_size - start and header[start:start+1] == b'\x08':
                candidates.append((start, size))
        if len(candidates) != 1:
            raise ValueError(f'{asset}: expected one uncooked NNE ONNX payload, found {len(candidates)}')
        start, size = candidates[0]
        src.seek(start)
        paths = []

        def copy_data(name, count):
            # Additional-file names originate in the package. Never allow path traversal.
            path = destination / name
            if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name:
                raise ValueError(f'Unsafe embedded path: {name}')
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            temp = path.with_name(path.name + '.tmp')
            with temp.open('wb') as out:
                while count:
                    chunk = src.read(min(count, 8 * 1024 * 1024))
                    if not chunk:
                        raise EOFError(asset)
                    digest.update(chunk)
                    out.write(chunk)
                    count -= len(chunk)
            temp.replace(path)
            paths.append({'file': name, 'sha256': digest.hexdigest(), 'bytes': path.stat().st_size})

        copy_data(asset.stem + '.onnx', size)
        count = struct.unpack('<i', src.read(4))[0]
        if not 0 <= count <= 100:
            raise ValueError(f'Unsupported AdditionalFileData count: {count}')
        for _ in range(count):
            length = struct.unpack('<i', src.read(4))[0]
            if not 0 < abs(length) < 4096:
                raise ValueError('Invalid NNE FString length')
            name = src.read(abs(length) * (2 if length < 0 else 1)).decode('utf-16-le' if length < 0 else 'utf-8').rstrip('\0')
            size = struct.unpack('<q', src.read(8))[0]
            if not 0 <= size <= asset.stat().st_size - src.tell():
                raise ValueError('Invalid additional payload length')
            copy_data(name, size)
    return {'asset': str(asset), 'payload_offset': start, 'files': paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, default=Path(r'D:\UE\UE_5.8'))
    parser.add_argument('--output', type=Path, default=Path('models'))
    args = parser.parse_args()
    root = args.engine / 'Engine/Plugins/Marketplace/MetaHumanBodyTracker_5.8/Content/Models/Offline'
    if not root.is_dir():
        parser.error(f'Model directory not found: {root}')
    manifest = []
    for asset in sorted(root.glob('*.uasset')):
        print('Extracting', asset.name, flush=True)
        manifest.append(extract(asset, args.output))
    resolve_external_data(args.output)
    for entry in manifest:
        runtime_path = args.output/(Path(entry['asset']).stem+'.onnx')
        with runtime_path.open('rb') as stream:
            entry['runtime_onnx_sha256'] = hashlib.file_digest(stream,'sha256').hexdigest()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Extracted', len(manifest), 'models; no Unreal process used.', flush=True)


if __name__ == '__main__':
    main()
