'''
PyLisC: import/output utilities
'''

# Import external libraries
import mrcfile, numpy as np
from pathlib import Path


def nameOutputFile(input_path, mode):
    base_stem = f'{input_path.stem}_PyLisC_{mode}'
    output_mrc = Path(f'{input_path.parents[0]}/{base_stem}.mrc')
    if output_mrc.exists():
        counter = 1
        while True:
            output_mrc = Path(f'{input_path.parents[0]}/{base_stem}_{counter}.mrc')
            if not output_mrc.exists():
                break
            counter += 1
    return(output_mrc)

def readMrcFile(path: Path):
    with mrcfile.open(path, permissive=True) as mrc:
        data = mrc.data.astype(np.float32)
        voxel_size = mrc.voxel_size # in Ångstroms
    if data.ndim == 2:
        data = data[np.newaxis, ...]
    return data, voxel_size

def writeMrcFile(data, voxel_size, path: Path):
    with mrcfile.new(path, overwrite=True) as out:
        out.set_data(data.astype(np.float32))
        out.voxel_size = voxel_size

def find_tilt_series(input_dir, pattern: str = '*.mrc'):
    '''
    Recursively find tilt series MRCs under input_dir, excluding PyLisC's own output
    '''
    return sorted(
        p for p in input_dir.rglob(pattern)
        if '_PyLisC_' not in p.stem
    )