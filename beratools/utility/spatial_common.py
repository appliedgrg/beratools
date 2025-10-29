"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file is intended to be hosting common spatial classes/functions for BERA Tools
"""
import argparse
import json
import warnings

import geopandas as gpd
import numpy as np
import osgeo
import pyogrio
import pyproj
import rasterio
from osgeo import gdal
from rasterio import mask

import beratools.core.constants as bt_const

# suppress pandas UserWarning: Geometry column contains no geometry when splitting lines
warnings.simplefilter(action="ignore", category=UserWarning)

# restore .shx for shapefile for using GDAL or pyogrio
gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
pyogrio.set_gdal_config_options({"SHAPE_RESTORE_SHX": "YES"})

# suppress all kinds of warnings
if not bt_const.BT_DEBUGGING:
    gdal.SetConfigOption("CPL_LOG", "NUL")  # GDAL warning
    warnings.filterwarnings("ignore")  # suppress warnings
    warnings.simplefilter(action="ignore", category=UserWarning)  # suppress Pandas UserWarning

def clip_raster(
    in_raster_file,
    clip_geom,
    buffer=0.0,
    out_raster_file=None,
    default_nodata=bt_const.BT_NODATA,
):
    out_meta = None
    with rasterio.open(in_raster_file) as raster_file:
        out_meta = raster_file.meta
        ras_nodata = out_meta["nodata"]
        if ras_nodata is None:
            ras_nodata = default_nodata

        clip_geo_buffer = [clip_geom.buffer(buffer)]
        out_image: np.ndarray
        out_image, out_transform = mask.mask(
            raster_file, clip_geo_buffer, crop=True, nodata=ras_nodata, filled=True
        )
        if np.isnan(ras_nodata):
            out_image[np.isnan(out_image)] = default_nodata

        elif np.isinf(ras_nodata):
            out_image[np.isinf(out_image)] = default_nodata
        else:
            out_image[out_image == ras_nodata] = default_nodata

        out_image = np.ma.masked_where(out_image == default_nodata, out_image)
        out_image.fill_value = default_nodata
        ras_nodata = default_nodata

        height, width = out_image.shape[1:]

        out_meta.update(
            {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "transform": out_transform,
                "nodata": ras_nodata,
            }
        )

    if out_raster_file:
        with rasterio.open(out_raster_file, "w", **out_meta) as dest:
            dest.write(out_image)
            print("[Clip raster]: data saved to {}.".format(out_raster_file))

    return out_image, out_meta

def check_arguments():
    # Get tool arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=json.loads)
    parser.add_argument("-p", "--processes")
    parser.add_argument("-v", "--verbose")
    args = parser.parse_args()

    verbose = True if args.verbose == "True" else False
    for item in args.input:
        if args.input[item].lower() == "false":
            args.input[item] = False
        elif args.input[item].lower() == "true":
            args.input[item] = True

    return args, verbose


def vector_crs(in_vector):
    osr_crs = osgeo.osr.SpatialReference()
    from pyproj.enums import WktVersion

    vec_crs = None
    # open input vector data as GeoDataFrame
    gpd_vector = gpd.GeoDataFrame.from_file(in_vector)
    try:
        if gpd_vector.crs is not None:
            vec_crs = gpd_vector.crs
            if osgeo.version_info.major < 3:
                osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
            else:
                osr_crs.ImportFromEPSG(vec_crs.to_epsg())
            return osr_crs
        else:
            print("No CRS found in the input feature, please check!")
            exit()
    except Exception as e:
        print(e)
        exit()


def raster_crs(in_raster):
    osr_crs = osgeo.osr.SpatialReference()
    with rasterio.open(in_raster) as raster_file:
        from pyproj.enums import WktVersion

        try:
            if raster_file.crs is not None:
                vec_crs = raster_file.crs
                if osgeo.version_info.major < 3:
                    osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
                else:
                    osr_crs.ImportFromEPSG(vec_crs.to_epsg())
                return osr_crs
            else:
                print("No Coordinate Reference System (CRS) find in the input feature, please check!")
                exit()
        except Exception as e:
            print(e)
            exit()


def compare_crs(crs_org, crs_dst):
    if crs_org and crs_dst:
        if crs_org.IsSameGeogCS(crs_dst):
            print("Check: Input file Spatial Reference are the same, continue.")
            return True
        else:
            crs_org_norm = pyproj.CRS(crs_org.ExportToWkt())
            crs_dst_norm = pyproj.CRS(crs_dst.ExportToWkt())
            if crs_org_norm.is_compound:
                crs_org_proj = crs_org_norm.sub_crs_list[0].coordinate_operation.name
            elif crs_org_norm.name == "unnamed":
                return False
            else:
                crs_org_proj = crs_org_norm.coordinate_operation.name

            if crs_dst_norm.is_compound:
                crs_dst_proj = crs_dst_norm.sub_crs_list[0].coordinate_operation.name
            elif crs_org_norm.name == "unnamed":
                return False
            else:
                crs_dst_proj = crs_dst_norm.coordinate_operation.name

            if crs_org_proj == crs_dst_proj:
                if crs_org_norm.name == crs_dst_norm.name:
                    print("Input files Spatial Reference are the same, continue.")
                    return True
                else:
                    print(
                        """Checked: Data are on the same projected Zone but using 
                        different Spatial Reference. \n Consider to re-project 
                        all data onto same spatial reference system.\n Process Stop."""
                    )
                    exit()
            else:
                return False

    return False

