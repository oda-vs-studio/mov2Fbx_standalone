"""Intersect camera validity with the intervals containing one or two tracked actors."""
import json
import shutil
import numpy as np


def partition_tracks(tracks, first, last):
    intervals=[];skipped=[];start=first;previous=None
    masks=[t['valid'] if 'valid' in t else np.ones(last,dtype=bool) for t in tracks]
    for i in range(first,last+1):
        active=tuple(j for j,mask in enumerate(masks) if mask[i]) if i<last else None
        if i==first:previous=active;continue
        if active!=previous:
            reason='No tracked person' if not previous else 'More than two simultaneous tracked IDs' if len(previous)>2 else 'Fewer than 12 continuous frames' if i-start<12 else None
            if reason:skipped.append(dict(start=start,end=i,reason=reason))
            else:intervals.append(dict(start=start,end=i,track_indices=list(previous)))
            start=i;previous=active
    return intervals,skipped


def prepare_intervals(status,tracks,camera_dir):
    # Legacy cached full-clip tracking remains valid without re-partitioning.
    if not any('valid' in t for t in tracks):return status,[]
    entries=[];skipped=[]
    for camera in status['segments']:
        intervals,missing=partition_tracks(tracks,camera['start'],camera['end']);skipped+=missing
        for interval in intervals:
            first,last=interval['start'],interval['end']
            entry={**camera,**interval,'id':len(entries)+1,'frames':last-first}
            if (first,last)!=(camera['start'],camera['end']):
                source=camera_dir/camera['camera_dir']
                dest=camera_dir/'tracked_intervals'/f'{first:06d}_{last:06d}'
                dest.mkdir(parents=True);(dest/'depth').mkdir()
                offset=first-camera['start'];end=last-camera['start']
                with np.load(source/'trajectory.npz') as data:
                    values={key:data[key] for key in data.files}
                values['w2c']=values['w2c'][offset:end];values['frame_indices']=np.arange(first,last)
                np.savez_compressed(dest/'trajectory.npz',**values)
                for j,i in enumerate(range(offset,end)):
                    shutil.copyfile(source/'depth'/f'{i:06d}.npz',dest/'depth'/f'{j:06d}.npz')
                entry['camera_dir']=str(dest.relative_to(camera_dir))
            entries.append(entry)
    result={**status,'segments':entries,'partial':status['partial'] or bool(skipped) or len(entries)!=1}
    (camera_dir/'tracking_intervals.json').write_text(json.dumps(dict(segments=entries,skipped=skipped),indent=2))
    return result,skipped
