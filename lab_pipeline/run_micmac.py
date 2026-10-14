#!/usr/bin/env python3
"""Run an independent classic MicMac photogrammetry workflow with checkpoints."""
import argparse
import collections
import fcntl
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/volume/wzhang/mesh-research-workspace/micmac')
RUN = ROOT / 'lab_runs/mangrove-077-full405'
MM3D = ROOT / 'bin/mm3d'
PATTERN = r'DJI_.*\.JPG'

def utc():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)

def orientation_count(name):
    return len(list((RUN / ('Ori-' + name)).glob('Orientation-*.xml')))

def checkpoint_transition(state, signature, allow_recovery):
    previous = state.get('signature')
    if previous is None or previous == signature:
        return None
    normalized = dict(previous)
    normalized.setdefault('ba_calibration_mode', 'all')
    if normalized == signature:
        return 'record_legacy_all_mode'
    comparable = dict(normalized)
    comparable['ba_calibration_mode'] = signature['ba_calibration_mode']
    stages = state.get('stages', {})
    earlier_complete = all(stages.get(name, {}).get('status') == 'complete' for name in (
        '01_gps_text', '02_gps_local', '03_gps_neighbors', '04_tie_points',
        '05_sfm', '06_gps_alignment'))
    later_started = any(name[:2].isdigit() and int(name[:2]) > 7 for name in stages)
    if (allow_recovery and comparable == signature and
            normalized['ba_calibration_mode'] == 'all' and signature['ba_calibration_mode'] == 'fixed' and
            state.get('status') == 'failed' and
            stages.get('07_bundle_adjustment', {}).get('status') == 'failed' and
            earlier_complete and not later_started):
        return 'recover_failed_all_free_ba_with_fixed_sfm_calibration'
    raise RuntimeError('Existing checkpoints have different inputs or parameters; select a new run directory')

def main():
    global ROOT, RUN, MM3D
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--dataset', default='mangrove-077')
    parser.add_argument('--run-name', default='mangrove-077-full405')
    parser.add_argument('--expected-count', type=int, default=405)
    parser.add_argument('--threads', type=int, default=64)
    parser.add_argument('--resolution', type=float, default=0.03)
    parser.add_argument('--gps-sigma', type=float, default=5.0)
    parser.add_argument('--neighbor-distance', type=float, default=100.0)
    parser.add_argument('--ba-calibration-mode', choices=('fixed', 'all'), default='fixed')
    parser.add_argument('--recover-failed-ba', action='store_true',
        help='Permit only a failed AllFree BA to retry with the existing SfM calibration fixed')
    parser.add_argument('--stop-after', default=None)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    RUN = ROOT / 'lab_runs' / args.run_name
    MM3D = ROOT / 'bin/mm3d'
    if args.resolution <= 0 or args.threads <= 0:
        raise ValueError('Resolution and thread count must be positive')
    RUN.mkdir(parents=True, exist_ok=True)
    lock = (RUN / 'pipeline.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    logs = RUN / 'logs'
    logs.mkdir(exist_ok=True)
    output = RUN / 'OUTPUT'
    output.mkdir(exist_ok=True)
    status_path = RUN / 'status.json'
    state = json.loads(status_path.read_text()) if status_path.exists() else {'stages': {}}
    data = ROOT / 'lab_data' / args.dataset
    metadata_path = data / 'metadata.json'
    metadata = json.loads(metadata_path.read_text())
    expected = args.expected_count
    if len(metadata) != expected:
        raise RuntimeError(f'The full {expected}-photograph input is required')
    signature = {'dataset': args.dataset, 'expected_count': expected, 'resolution': args.resolution,
        'gps_sigma': args.gps_sigma, 'neighbor_distance': args.neighbor_distance,
        'metadata_sha256': hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        'source_revision': (ROOT / '.lab/upstream_revision.txt').read_text().strip(),
        'ba_calibration_mode': args.ba_calibration_mode}
    transition = checkpoint_transition(state, signature, args.recover_failed_ba)
    if transition and transition != 'record_legacy_all_mode':
        history = RUN / 'recovery_history' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        history.mkdir(parents=True, exist_ok=False)
        for old in (status_path, RUN / 'config.json', logs / '07_bundle_adjustment.log'):
            if old.exists():
                shutil.copy2(old, history / old.name)
        write_json(history / 'recovery.json', {'reason': transition, 'updated_utc': utc(),
            'previous_signature': state['signature'], 'new_signature': signature,
            'preserved_stages': ['01', '02', '03', '04', '05', '06']})
        state.setdefault('recoveries', []).append({'reason': transition, 'history': str(history)})
    state['signature'] = signature
    for row in metadata:
        name = Path(row['SourceFile']).name
        original = data / 'images' / name
        link = RUN / name
        if not link.exists():
            link.symlink_to(original)
        if link.resolve() != original.resolve():
            raise RuntimeError(f'Unexpected input link: {name}')
        if any(key not in row for key in ('GPSLatitude', 'GPSLongitude', 'GPSAltitude', 'GimbalPitchDegree')):
            raise RuntimeError(f'Incomplete GPS or gimbal metadata: {name}')
    if len(list(RUN.glob('*.JPG'))) != expected:
        raise RuntimeError('Run directory photo count differs from dataset')
    nadir = [Path(r['SourceFile']).name for r in metadata if float(r.get('GimbalPitchDegree', 0)) <= -75]
    if not nadir:
        raise RuntimeError('No near-nadir images are available for the orthophoto')
    nadir_regex = '(' + '|'.join(re.escape(n) for n in nadir) + ')'
    models = collections.defaultdict(list)
    for row in metadata:
        models[row['Model']].append(row)
    # The local profile is a fallback when 35 mm equivalent EXIF is unavailable.
    # Native MicMac prefers existing 35 mm equivalent EXIF for initialization.
    descriptor = ET.Element('ChantierDescripteur')
    database = ET.SubElement(descriptor, 'LocCamDataBase')
    camera_profiles = []
    for model, rows in sorted(models.items()):
        row = rows[0]
        if len({(r['ImageWidth'], r['ImageHeight'], r['FocalLength']) for r in rows}) != 1:
            raise RuntimeError(f'Model {model} has mixed dimensions or focal lengths; needs separate calibration groups')
        f35 = row.get('FocalLengthIn35mmFormat')
        native_focal = (float(f35) * math.hypot(int(row['ImageWidth']), int(row['ImageHeight']))
            / math.hypot(36, 24)) if f35 else float(row['CalibratedFocalLength'])
        reference_focal = float(row.get('CalibratedFocalLength', native_focal))
        width = float(row['FocalLength']) * int(row['ImageWidth']) / reference_focal
        height = float(row['FocalLength']) * int(row['ImageHeight']) / reference_focal
        entry = ET.SubElement(database, 'CameraEntry')
        ET.SubElement(entry, 'Name').text = model
        ET.SubElement(entry, 'SzCaptMm').text = f'{width:.12f} {height:.12f}'
        ET.SubElement(entry, 'ShortName').text = 'DJI_' + re.sub(r'\W+', '_', model)
        camera_profiles.append({'model': model, 'effective_sensor_mm': [width, height],
            'fallback_profile_source': 'DJI CalibratedFocalLength and original EXIF focal length',
            'reference_dji_focal_pixels': row.get('CalibratedFocalLength'),
            'native_initial_focal_pixels': native_focal,
            'native_initialization_source': '35 mm equivalent EXIF' if f35 else 'local camera profile',
            'self_calibration': True})
    ET.indent(descriptor)
    ET.ElementTree(descriptor).write(RUN / 'MicMac-LocalChantierDescripteur.xml', encoding='utf-8', xml_declaration=True)
    lon = sum(float(r['GPSLongitude']) for r in metadata) / len(metadata)
    lat = sum(float(r['GPSLatitude']) for r in metadata) / len(metadata)
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    proj = f'+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs' + (' +south' if lat < 0 else '')
    system = ET.Element('SystemeCoord')
    bsc = ET.SubElement(system, 'BSC')
    ET.SubElement(bsc, 'TypeCoord').text = 'eTC_Proj4'
    ET.SubElement(bsc, 'AuxR').text = '1'
    ET.SubElement(bsc, 'AuxR').text = '1'
    ET.SubElement(bsc, 'AuxR').text = '1'
    ET.SubElement(bsc, 'AuxStr').text = proj
    ET.indent(system)
    ET.ElementTree(system).write(RUN / 'SysPROJ.xml', encoding='utf-8', xml_declaration=True)
    config = vars(args) | {'root': str(ROOT), 'run': str(RUN), 'input_count': len(metadata),
        'nadir_ortho_count': len(nadir), 'epsg': epsg, 'projection': proj,
        'camera_profiles': camera_profiles,
        'upstream_revision': (ROOT / '.lab/upstream_revision.txt').read_text().strip(),
        'all_photos_used_for_sfm': True, 'ortho_uses_near_nadir_photos': True,
        'uses_odx_cameras_or_geometry': False}
    write_json(RUN / 'config.json', config)
    (RUN / 'nadir_images.txt').write_text('\n'.join(nadir) + '\n')
    env = os.environ.copy()
    env.update({'PATH': str(ROOT / 'bin') + os.pathsep + env['PATH'],
        'MICMAC_MAX_THREADS': str(args.threads), 'OMP_NUM_THREADS': '1',
        'MAGICK_THREAD_LIMIT': '1', 'OPENBLAS_NUM_THREADS': '1', 'LC_ALL': 'C'})
    state.update({'status': 'running', 'pid': os.getpid(), 'updated_utc': utc(), 'config': config})
    write_json(status_path, state)

    def step(name, command, check=None):
        existing = state['stages'].get(name, {})
        if existing.get('status') == 'complete' and (check is None or check()):
            print(f'SKIP {name}: verified checkpoint', flush=True)
            return
        stage = {'status': 'running', 'started_utc': utc(), 'command': command}
        state['stage'] = name
        state['stages'][name] = stage
        state['updated_utc'] = utc()
        write_json(status_path, state)
        print(f'START {name}: {shlex.join(command)}', flush=True)
        started = time.monotonic()
        with (logs / (name + '.log')).open('a') as log:
            log.write(f'\n[{utc()}] {shlex.join(command)}\n')
            log.flush()
            # Closing stdin prevents unattended MicMac errors waiting for Enter.
            result = subprocess.run(command, cwd=RUN, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT)
        stage.update({'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - started,
            'finished_utc': utc()})
        if result.returncode != 0 or (check is not None and not check()):
            stage['status'] = 'failed'
            state.update({'status': 'failed', 'updated_utc': utc()})
            write_json(status_path, state)
            raise RuntimeError(f'{name} failed; inspect {logs / (name + ".log")}')
        stage['status'] = 'complete'
        state['updated_utc'] = utc()
        write_json(status_path, state)
        print(f'COMPLETE {name} ({stage["elapsed_seconds"]:.1f}s)', flush=True)
        if args.stop_after == name:
            state.update({'status': 'stopped_at_requested_stage', 'updated_utc': utc()})
            write_json(status_path, state)
            raise SystemExit(0)

    def dense_outputs_complete():
        orthos = RUN / 'Ortho-MEC-Malt'
        files = [orthos / 'MTDOrtho.xml', orthos / 'MTDMaskOrtho.xml',
                 RUN / 'MEC-Malt/Z_Num9_DeZoom2_STD-MALT.tif',
                 RUN / 'MEC-Malt/Z_Num9_DeZoom2_STD-MALT.xml']
        files += [orthos / f'{prefix}_{Path(name).stem}.tif'
                  for name in nadir for prefix in ('Ort', 'PC', 'Incid')]
        files += [orthos / f'PC_{Path(name).stem}.xml' for name in nadir]
        if not all(path.is_file() and path.stat().st_size > 0 for path in files):
            return False
        return all(ET.parse(orthos / f'PC_{Path(name).stem}.xml').getroot().findtext('.//Done') == 'true'
                   for name in nadir)

    try:
        step('01_gps_text', [str(MM3D), 'XifGps2Txt', PATTERN], lambda: (RUN / 'GpsCoordinatesFromExif.txt').exists())
        step('02_gps_local', [str(MM3D), 'XifGps2Xml', PATTERN, 'RAWGNSS'],
            lambda: orientation_count('RAWGNSS') == expected and (RUN / 'RTLFromExif.xml').exists())
        step('03_gps_neighbors', [str(MM3D), 'OriConvert', '#F=N X Y Z', 'GpsCoordinatesFromExif.txt', 'RAWGNSS_N',
            'ChSys=DegreeWGS84@RTLFromExif.xml', 'MTD1=1', 'NameCple=FileImagesNeighbour.xml',
            f'DN={args.neighbor_distance}', 'OkNoIm=1'], lambda: (RUN / 'FileImagesNeighbour.xml').exists())
        step('04_tie_points', [str(MM3D), 'Tapioca', 'File', 'FileImagesNeighbour.xml', '2640', f'ByP={args.threads}'],
            lambda: any((RUN / 'Homol').glob('Pastis*/*.dat')))
        step('05_sfm', [str(MM3D), 'Tapas', 'FraserBasic', PATTERN, 'Out=Arbitrary'],
            lambda: orientation_count('Arbitrary') == expected)
        step('06_gps_alignment', [str(MM3D), 'CenterBascule', PATTERN, 'Arbitrary', 'RAWGNSS_N', 'Ground_Init_RTL'],
            lambda: orientation_count('Ground_Init_RTL') == expected)
        step('07_bundle_adjustment', [str(MM3D), 'Campari', PATTERN, 'Ground_Init_RTL', 'Ground_RTL',
            f'EmGPS=[RAWGNSS_N,{args.gps_sigma}]',
            'AllFree=' + ('0' if args.ba_calibration_mode == 'fixed' else '1')],
            lambda: orientation_count('Ground_RTL') == expected)
        step('08_projected_coordinates', [str(MM3D), 'ChgSysCo', PATTERN, 'Ground_RTL',
            'RTLFromExif.xml@SysPROJ.xml', 'Ground_PROJ'], lambda: orientation_count('Ground_PROJ') == expected)
        step('09_dense_and_orthorectification', [str(MM3D), 'Malt', 'Ortho', PATTERN, 'Ground_PROJ',
            f'ResolTerrain={args.resolution}', 'EZA=1', 'ZoomF=2', f'NbProc={args.threads}',
            'Purge=0', 'ImOrtho=' + nadir_regex], dense_outputs_complete)
        step('10_mosaic', [str(MM3D), 'Tawny', 'Ortho-MEC-Malt', 'RadiomEgal=0'],
            lambda: (RUN / 'Ortho-MEC-Malt/Orthophotomosaic.tif').exists())
        step('11_geotiff', ['gdal_translate', '-a_srs', f'EPSG:{epsg}', '-co', 'TILED=YES',
            '-co', 'COMPRESS=DEFLATE', '-co', 'BIGTIFF=IF_SAFER',
            'Ortho-MEC-Malt/Orthophotomosaic.tif', 'OUTPUT/Mangrove-077_MicMac_orthophoto.tif'],
            lambda: (output / 'Mangrove-077_MicMac_orthophoto.tif').is_file() and
                (output / 'Mangrove-077_MicMac_orthophoto.tif').stat().st_size > 1000)
        step('12_preview', ['gdal_translate', '-of', 'PNG', '-outsize', '2000', '0',
            'OUTPUT/Mangrove-077_MicMac_orthophoto.tif', 'OUTPUT/Mangrove-077_MicMac_orthophoto_preview.png'],
            lambda: (output / 'Mangrove-077_MicMac_orthophoto_preview.png').exists())
        info = subprocess.check_output(['gdalinfo', '-json', str(output / 'Mangrove-077_MicMac_orthophoto.tif')], text=True)
        write_json(output / 'orthophoto_gdalinfo.json', json.loads(info))
        write_json(output / 'result_summary.json', {'finished_utc': utc(), 'input_count': expected,
            'registered_camera_count': orientation_count('Ground_PROJ'), 'nadir_ortho_count': len(nadir),
            'epsg': epsg, 'orthophoto': str(output / 'Mangrove-077_MicMac_orthophoto.tif'),
            'uses_odx_cameras_or_geometry': False,
            'limitations': ['No independent ground control accuracy verification',
                'Static scene reconstruction does not correct moving vehicles automatically',
                'Unobserved surfaces cannot be recovered with a factual accuracy guarantee']})
        state.update({'status': 'complete', 'updated_utc': utc()})
        write_json(status_path, state)
        print('PIPELINE_COMPLETE', flush=True)
    except Exception:
        state.update({'status': 'failed', 'updated_utc': utc(), 'error': traceback.format_exc()})
        write_json(status_path, state)
        raise

if __name__ == '__main__':
    main()
