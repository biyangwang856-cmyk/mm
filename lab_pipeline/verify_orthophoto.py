#!/usr/bin/env python3
"""Verify the actual exported raster, without asserting ground-control accuracy."""
import hashlib
import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

ROOT = Path('/volume/wzhang/mesh-research-workspace/micmac')
RUN = ROOT / 'lab_runs/mangrove-077-full405'
OUTPUT = RUN / 'OUTPUT'


def main():
    global ROOT, RUN, OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--run-name', default='mangrove-077-full405')
    args = parser.parse_args()
    ROOT = args.root.resolve()
    RUN = ROOT / 'lab_runs' / args.run_name
    OUTPUT = RUN / 'OUTPUT'
    gdal.UseExceptions()
    state = json.loads((RUN / 'status.json').read_text())
    if state.get('status') != 'complete':
        raise RuntimeError('The complete reconstruction pipeline must finish first')
    filename = OUTPUT / 'Mangrove-077_MicMac_orthophoto.tif'
    raster = gdal.Open(str(filename))
    assert raster.RasterXSize > 128 and raster.RasterYSize > 128
    assert raster.RasterCount >= 3
    transform = raster.GetGeoTransform()
    assert transform[1] > 0 and transform[5] < 0, transform
    assert transform[2] == 0 and transform[4] == 0, transform
    assert abs(transform[1] - state['config']['resolution']) < 1e-8
    assert abs(abs(transform[5]) - state['config']['resolution']) < 1e-8
    target = osr.SpatialReference(wkt=raster.GetProjection())
    target.AutoIdentifyEPSG()
    expected = str(state['config']['epsg'])
    assert target.GetAuthorityCode(None) == expected
    bounds = [transform[0], transform[3] + raster.RasterYSize * transform[5],
              transform[0] + raster.RasterXSize * transform[1], transform[3]]
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    mapping = osr.CoordinateTransformation(source, target)
    metadata = json.loads((ROOT / 'lab_data' / state['config']['dataset'] / 'metadata.json').read_text())
    points = [mapping.TransformPoint(float(row['GPSLongitude']), float(row['GPSLatitude']))
              for row in metadata]
    center = [float(np.mean([p[i] for p in points])) for i in (0, 1)]
    gps_bounds = [min(p[0] for p in points), min(p[1] for p in points),
                  max(p[0] for p in points), max(p[1] for p in points)]
    assert bounds[0] <= gps_bounds[2] and bounds[2] >= gps_bounds[0], (bounds, gps_bounds)
    assert bounds[1] <= gps_bounds[3] and bounds[3] >= gps_bounds[1], (bounds, gps_bounds)
    cameras = []
    rotation_errors = []
    calibration_files = set()
    for path in sorted((RUN / 'Ori-Ground_PROJ').glob('Orientation-*.xml')):
        camera = ET.parse(path).getroot()
        center_text = camera.findtext('.//Externe/Centre')
        rotation = np.array([[float(value) for value in camera.findtext(
            './/Externe/ParamRotation/CodageMatr/' + row).split()] for row in ('L1', 'L2', 'L3')])
        center_xyz = [float(value) for value in center_text.split()]
        assert np.isfinite(center_xyz).all() and np.isfinite(rotation).all(), path
        error = float(np.max(np.abs(rotation @ rotation.T - np.eye(3))))
        assert error < 1e-4 and abs(np.linalg.det(rotation) - 1) < 1e-4, path
        cameras.append(center_xyz)
        rotation_errors.append(error)
        calibration_files.add(camera.findtext('.//FileInterne'))
    calibrations = []
    for relative in sorted(calibration_files):
        calibration = ET.parse(RUN / relative).getroot()
        focal = float(calibration.findtext('.//F'))
        principal = [float(value) for value in calibration.findtext('.//PP').split()]
        dimensions = [int(value) for value in calibration.findtext('.//SzIm').split()]
        assert focal > 0 and np.isfinite([focal] + principal).all()
        calibrations.append({'file': relative, 'focal_pixels': focal,
                             'principal_point_pixels': principal, 'image_size_pixels': dimensions})
    sample_width = min(1600, raster.RasterXSize)
    sample_height = max(1, round(raster.RasterYSize * sample_width / raster.RasterXSize))
    sample = raster.ReadAsArray(buf_xsize=sample_width, buf_ysize=sample_height,
                               band_list=[1, 2, 3])
    assert np.isfinite(sample).all()
    assert float(sample.std()) > 1, 'Raster has no substantial RGB variation'
    digest = hashlib.sha256()
    with filename.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    report = {
        'verified_utc': datetime.now(timezone.utc).isoformat(),
        'verified': True,
        'file': str(filename), 'bytes': filename.stat().st_size,
        'sha256': digest.hexdigest(),
        'size_pixels': [raster.RasterXSize, raster.RasterYSize],
        'bands': raster.RasterCount, 'epsg': int(expected),
        'pixel_spacing_m': [transform[1], abs(transform[5])],
        'projected_bounds_m': bounds,
        'photo_gps_center_projected_m': center,
        'registered_cameras': len(cameras),
        'individual_rgb_orthos': len(list((RUN / 'Ortho-MEC-Malt').glob('Ort_*.tif'))),
        'camera_center_range_projected_m': {'min': np.min(cameras, axis=0).tolist(),
                                             'max': np.max(cameras, axis=0).tolist()},
        'max_rotation_orthogonality_error': max(rotation_errors),
        'optimized_calibrations': calibrations,
        'upstream_revision': (ROOT / '.lab/upstream_revision.txt').read_text().strip(),
        'verification_code_commit': subprocess.check_output(
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'rgb_sample_standard_deviation': float(sample.std()),
        'scope': 'File integrity, readable nonconstant pixels and plausible georeferencing; '
                 'does not validate absolute survey accuracy or image quality against a reference.'
    }
    sfm_log = (RUN / 'logs/05_sfm.log').read_text(errors='replace')
    initial = re.search(r'MdPppppF=\s*([0-9.eE+-]+)', sfm_log)
    report['native_sfm_initial_focal_pixels_from_log'] = float(initial.group(1)) if initial else None
    report['dji_reference_focal_pixels'] = sorted({float(row['CalibratedFocalLength']) for row in metadata
                                                 if 'CalibratedFocalLength' in row})
    assert report['registered_cameras'] == state['config']['input_count']
    assert report['individual_rgb_orthos'] == state['config']['nadir_ortho_count']
    (OUTPUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    subprocess.run(['/usr/bin/python3', str(ROOT / 'lab_pipeline/render_details.py'),
                    '--run', str(RUN)], check=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
