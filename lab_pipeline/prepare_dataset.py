#!/usr/bin/env python3
"""Copy a complete photo set and its navigation files, verifying independent copies."""
import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--dataset', default='mangrove-077')
    parser.add_argument('--expected-count', type=int, default=405)
    parser.add_argument('--copy-only', action='store_true')
    args = parser.parse_args()
    root, source = args.root.resolve(), args.source.resolve()
    target = root / 'lab_data' / args.dataset
    images = target / 'images'
    ancillary = target / 'ancillary'
    originals = sorted(path for path in source.iterdir() if path.is_file())
    photos = [path for path in originals if path.suffix.lower() in ('.jpg', '.jpeg')]
    if len(photos) != args.expected_count:
        raise RuntimeError(f'Expected {args.expected_count} input photos; found {len(photos)}')
    images.mkdir(parents=True, exist_ok=True)
    ancillary.mkdir(exist_ok=True)
    records = []
    for index, original in enumerate(originals, 1):
        copied = (images if original in photos else ancillary) / original.name
        if not copied.exists():
            shutil.copy2(original, copied)
        source_digest, copied_digest = checksum(original), checksum(copied)
        if source_digest != copied_digest or original.samefile(copied):
            raise RuntimeError(f'Independent copy verification failed: {original.name}')
        records.append({'name': original.name, 'kind': 'photo' if original in photos else 'ancillary',
                        'bytes': copied.stat().st_size, 'sha256': copied_digest,
                        'copied_path': str(copied)})
        if index % 25 == 0 or index == len(originals):
            print(f'COPY_VERIFIED {index}/{len(originals)}', flush=True)
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'source_directory': str(source), 'photo_directory': str(images),
                'photo_count': len(photos), 'ancillary_count': len(originals) - len(photos),
                'independent_copies': True, 'files': records}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if args.copy_only:
        print('ALL_INPUT_COPIES_VERIFIED', flush=True)
        return
    tags = ['Make', 'Model', 'LensModel', 'ImageWidth', 'ImageHeight', 'FocalLength',
            'FocalLengthIn35mmFormat', 'GPSLatitude', 'GPSLongitude', 'GPSAltitude',
            'GPSAltitudeRef', 'AbsoluteAltitude', 'RelativeAltitude', 'GimbalPitchDegree',
            'GimbalRollDegree', 'GimbalYawDegree', 'DewarpFlag', 'DewarpData',
            'CalibratedFocalLength', 'CalibratedOpticalCenterX', 'CalibratedOpticalCenterY',
            'RtkFlag', 'RtkStdLon', 'RtkStdLat', 'RtkStdHgt', 'DateTimeOriginal']
    command = ['exiftool', '-json', '-n'] + ['-' + tag for tag in tags] + [str(images / p.name) for p in photos]
    metadata_text = subprocess.check_output(command, text=True)
    metadata = json.loads(metadata_text)
    if len(metadata) != len(photos):
        raise RuntimeError('Incomplete metadata extraction')
    (target / 'metadata.json').write_text(metadata_text)
    summary = {'photo_count': len(metadata),
               'models': sorted({str(row.get('Model')) for row in metadata}),
               'dimensions': sorted({(row['ImageWidth'], row['ImageHeight']) for row in metadata}),
               'gps_count': sum('GPSLatitude' in row and 'GPSLongitude' in row for row in metadata),
               'nadir_count': sum(float(row.get('GimbalPitchDegree', 0)) <= -75 for row in metadata),
               'gimbal_pitches': sorted({row.get('GimbalPitchDegree') for row in metadata
                                         if row.get('GimbalPitchDegree') is not None}),
               'first_photo': metadata[0]}
    (target / 'metadata_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
