"""Render nine 1:1 pixel crops for visual inspection of the delivered raster."""
import argparse
import json
from pathlib import Path
import numpy as np
from osgeo import gdal

parser = argparse.ArgumentParser()
parser.add_argument('--run', type=Path, required=True)
args = parser.parse_args()
gdal.UseExceptions()
out = args.run / 'OUTPUT'
image = gdal.Open(str(out / 'Mangrove-077_MicMac_orthophoto.tif'))
edge = min(768, image.RasterXSize, image.RasterYSize)
atlas = np.zeros((3, edge * 3, edge * 3), dtype=np.uint8)
details = []
for row, fy in enumerate((0.25, 0.5, 0.75)):
    for col, fx in enumerate((0.25, 0.5, 0.75)):
        x = min(image.RasterXSize - edge, max(0, round(image.RasterXSize * fx - edge / 2)))
        y = min(image.RasterYSize - edge, max(0, round(image.RasterYSize * fy - edge / 2)))
        crop = image.ReadAsArray(x, y, edge, edge, band_list=[1, 2, 3])
        atlas[:, row * edge:(row + 1) * edge, col * edge:(col + 1) * edge] = crop
        details.append({'grid_row': row, 'grid_column': col, 'source_pixel_window': [x, y, edge, edge]})
memory = gdal.GetDriverByName('MEM').Create('', edge * 3, edge * 3, 3, gdal.GDT_Byte)
for band, color in enumerate((gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand), 1):
    memory.GetRasterBand(band).WriteArray(atlas[band - 1])
    memory.GetRasterBand(band).SetColorInterpretation(color)
gdal.GetDriverByName('PNG').CreateCopy(str(out / 'native_pixel_details_3x3.png'), memory)
(out / 'native_pixel_details_3x3.json').write_text(json.dumps({'resampled': False,
    'description': 'Nine 1:1 pixel crops; adjacency in the atlas does not mean adjacency in the scene',
    'source_file': str(out / 'Mangrove-077_MicMac_orthophoto.tif'), 'windows': details}, indent=2) + '\n')
print('NATIVE_PIXEL_DETAILS_READY', flush=True)
