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

import warnings

import geopandas as gpd
import numpy as np
import pyproj
import rasterio
from osgeo import gdal, ogr, osr, version_info
from pyogrio import set_gdal_config_options
from rasterio import mask

import beratools.core.constants as bt_const

# suppress pandas UserWarning: Geometry column contains no geometry when splitting lines
warnings.simplefilter(action="ignore", category=UserWarning)

# restore .shx for shapefile for using GDAL or pyogrio
gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
set_gdal_config_options({"SHAPE_RESTORE_SHX": "YES"})  # for pyogrio


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
        out_image = None
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


def decode_file_layer(encoded):
    """
    Decode encoded file|layer string into file path and layer name.

    Args:
        encoded (str): Encoded string like "file.shp|" or "C:/path/file.gpkg|layer"

    Returns:
        tuple: (file_path, layer_name) where layer_name is None if empty
    """
    if "|" in encoded:
        file_path, layer = encoded.rsplit("|", 1)
        layer_name = layer if layer else None
    elif "::" in encoded:
        file_path, layer = encoded.rsplit("::", 1)
        layer_name = layer if layer else None
    else:
        file_path = encoded
        layer_name = None
    return file_path, layer_name


def vector_crs(in_vector, gpd_layer):
    osr_crs = osr.SpatialReference()
    from pyproj.enums import WktVersion

    vec_crs = None
    # open input vector data as GeoDataFrame
    if gpd_layer != None:
        gpd_vector = gpd.GeoDataFrame.from_file(in_vector, layer=gpd_layer)
    else:
        gpd_vector = gpd.GeoDataFrame.from_file(in_vector)
    try:
        if gpd_vector.crs is not None:
            vec_crs = gpd_vector.crs
            if version_info.major < 3:
                osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
            else:
                epsg = vec_crs.to_epsg()
                if epsg is not None:
                    osr_crs.ImportFromEPSG(epsg)
                else:
                    osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
            return osr_crs
        else:
            print("No CRS found in the input feature, please check!")
            exit()
    except Exception as e:
        print(e)
        exit()


def raster_crs(in_raster):
    osr_crs = osr.SpatialReference()
    with rasterio.open(in_raster) as raster_file:
        from pyproj.enums import WktVersion

        try:
            if raster_file.crs is not None:
                vec_crs = raster_file.crs
                if version_info.major < 3:
                    osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
                else:
                    epsg = vec_crs.to_epsg()
                    if epsg is not None:
                        osr_crs.ImportFromEPSG(epsg)
                    else:
                        osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
                return osr_crs
            else:
                print("No Coordinate Reference System (CRS) find in the input feature, please check!")
                exit()
        except Exception as e:
            print(e)
            exit()


def get_crs_proj_name(crs_norm, label="crs"):
    import warnings

    if crs_norm.is_compound:
        op = crs_norm.sub_crs_list[0].coordinate_operation
        if op is None:
            warnings.warn(f"{label}.sub_crs_list[0].coordinate_operation is None; using 'unknown'")
            return "unknown"
        return op.name
    elif crs_norm.name == "unnamed":
        return None
    else:
        op = crs_norm.coordinate_operation
        if op is None:
            warnings.warn(f"{label}.coordinate_operation is None; using 'unknown'")
            return "unknown"
        return op.name


def compare_crs(crs_org, crs_dst):
    if crs_org and crs_dst:
        if crs_org.IsSameGeogCS(crs_dst):
            print("Check: Input file Spatial Reference are the same, continue.")
            return True
        else:
            crs_org_norm = pyproj.CRS(crs_org.ExportToWkt())
            crs_dst_norm = pyproj.CRS(crs_dst.ExportToWkt())

            crs_org_proj = get_crs_proj_name(crs_org_norm, "crs_org_norm")
            if crs_org_proj is None:
                return False

            crs_dst_proj = get_crs_proj_name(crs_dst_norm, "crs_dst_norm")
            if crs_dst_proj is None:
                return False

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


def _extents_overlap(ext1, ext2) -> bool:
    """Return whether two extents overlap."""
    minx1, miny1, maxx1, maxy1 = ext1
    minx2, miny2, maxx2, maxy2 = ext2
    return not (maxx1 < minx2 or minx1 > maxx2 or maxy1 < miny2 or miny1 > maxy2)


def _vector_extent_from_gpkg_contents(in_vector, layer_name):
    """Read vector extent from GeoPackage metadata when available."""
    ds = ogr.Open(in_vector)
    if ds is None:
        return None

    try:
        target_layer = layer_name
        if target_layer is None:
            layer0 = ds.GetLayerByIndex(0)
            if layer0 is None:
                return None
            target_layer = layer0.GetName()

        layer_sql_name = target_layer.replace("'", "''")
        sql = f"SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name = '{layer_sql_name}'"
        result = ds.ExecuteSQL(sql)
        if result is None:
            return None

        try:
            feat = result.GetNextFeature()
            if feat is None:
                return None

            min_x = feat.GetField("min_x")
            min_y = feat.GetField("min_y")
            max_x = feat.GetField("max_x")
            max_y = feat.GetField("max_y")
            if None in (min_x, min_y, max_x, max_y):
                return None

            return float(min_x), float(min_y), float(max_x), float(max_y)
        finally:
            ds.ReleaseResultSet(result)
    finally:
        ds = None


def get_vector_extent_fast(in_vector, layer_name=None):
    """Get vector extent with metadata-first strategy and safe fallback."""
    extent = None

    if str(in_vector).lower().endswith(".gpkg"):
        extent = _vector_extent_from_gpkg_contents(in_vector, layer_name)
        if extent is not None:
            return extent

    ds = ogr.Open(in_vector)
    if ds is None:
        return None

    try:
        layer = ds.GetLayerByName(layer_name) if layer_name else ds.GetLayerByIndex(0)
        if layer is None:
            return None

        extent_ogr = layer.GetExtent(force=0)
        if extent_ogr is None:
            extent_ogr = layer.GetExtent(force=1)
        if extent_ogr is None:
            return None

        min_x, max_x, min_y, max_y = extent_ogr
        return float(min_x), float(min_y), float(max_x), float(max_y)
    finally:
        ds = None


def get_raster_extent(in_raster):
    """Get raster extent as (minx, miny, maxx, maxy)."""
    with rasterio.open(in_raster) as raster_file:
        bounds = raster_file.bounds
        return float(bounds.left), float(bounds.bottom), float(bounds.right), float(bounds.top)


def check_vector_raster_extent_overlap(in_vector, in_layer, in_raster) -> bool:
    """Fast extent precheck for vector/raster overlap.

    Returns False only for definite disjoint extents. Returns True when overlap
    exists or extents cannot be determined.
    """
    vector_extent = get_vector_extent_fast(in_vector, in_layer)
    raster_extent = get_raster_extent(in_raster)

    if vector_extent is None or raster_extent is None:
        return True

    return _extents_overlap(vector_extent, raster_extent)


def check_vector_vector_extent_overlap(in_vector1, in_layer1, in_vector2, in_layer2) -> bool:
    """Fast extent precheck for vector/vector overlap.

    Returns False only for definite disjoint extents. Returns True when overlap
    exists or extents cannot be determined.
    """
    extent1 = get_vector_extent_fast(in_vector1, in_layer1)
    extent2 = get_vector_extent_fast(in_vector2, in_layer2)

    if extent1 is None or extent2 is None:
        return True

    return _extents_overlap(extent1, extent2)


def check_vector_raster_overlap(gdf, in_raster) -> bool:
    """Check whether vector geometries overlap a raster footprint."""
    from beratools.core.algo_common import generate_raster_footprint

    if gdf is None or gdf.empty:
        return False

    geometries = gdf["geometry"]
    footprint = generate_raster_footprint(in_raster, latlon=False)

    if footprint.is_empty:
        return False

    if all(footprint.contains(geometries)):
        return True

    if any(footprint.intersects(geometries)):
        print("[Warning]: Some input features are partially outside the raster footprint.")
        return True

    return False


def check_vector_vector_overlap(gdf1, gdf2) -> bool:
    """Check whether vector geometries in gdf1 overlap those in gdf2."""
    if gdf1 is None or gdf1.empty or gdf2 is None or gdf2.empty:
        return False

    geom1 = gdf1["geometry"]
    union2 = gdf2.geometry.union_all()

    if union2 is None or union2.is_empty:
        return False

    if all(union2.contains(geom1)):
        return True

    if any(union2.intersects(geom1)):
        print("[Warning]: Some input features are partially outside the reference footprint.")
        return True

    return False


def seedlines_within_chm_footprint(gdf, in_raster) -> bool:
    """Check whether seed lines overlap the CHM raster footprint."""
    return check_vector_raster_overlap(gdf, in_raster)
