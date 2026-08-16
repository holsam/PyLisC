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

def find_input_files(input_dir, pattern: str = '*.mrc', recursive: bool = True):
    '''
    Find input MRCs under input_dir, excluding PyLisC's own output, recursing into subdirectories when recursive=True
    '''
    glob = input_dir.rglob if recursive else input_dir.glob
    return sorted(
        p for p in glob(pattern)
        if '_PyLisC_' not in p.stem
    )