"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This file hosts alternate CHM clipping/filtering logic for centerline runs.
"""

import math

import numpy as np
import rasterio
from rasterio import mask
import scipy.ndimage as ndimage
import skimage as ski

import beratools.core.constants as bt_const


def alt_clip_and_filter_reginal_maxima_wGap(
    params,
    in_raster_file,
    clip_geom,
    buffer=1.0,
    default_nodata=bt_const.BT_NODATA,
):
    with rasterio.open(in_raster_file) as src:
        clip_geo_buffer = [clip_geom.buffer(buffer)]
        out_image, out_transform = mask.mask(src, clip_geo_buffer, crop=True)
        ras_nodata = src.meta["nodata"]

        if ras_nodata is None:
            ras_nodata = default_nodata

        # Generate mask for valid raster data.
        data_mask = ~(np.ma.masked_equal(out_image, ras_nodata).mask)
        # Fill unmasked data with 0, otherwise keep the original value.
        data_filled = np.where(data_mask, out_image, 0)

        # Calculate gaussian_filter sigma to remove sharp noise without removing small crowns.
        sigma = math.ceil(params["tree_radius"]) * 0.5
        smoothed_data = ndimage.gaussian_filter(data_filled, sigma=sigma)
        # Generate search tree crown footprint.
        footprint = ski.morphology.disk(math.ceil(params["tree_radius"]))
        footprint = footprint.reshape(-1, footprint.shape[0], footprint.shape[1])

        smooth_mask = ndimage.gaussian_filter(data_mask.astype(float), sigma=sigma)
        mask_normalization = smoothed_data / smooth_mask
        mask_normalization[~data_mask] = np.nan
        mask_normalization = np.ma.masked_invalid(mask_normalization)

        tree_tops_indices = ski.feature.peak_local_max(
            mask_normalization,
            min_distance=1,
            exclude_border=False,
            num_peaks_per_label=1,
            footprint=footprint,
        )
        if len(tree_tops_indices) > 0:
            mask_ = np.ma.zeros_like(mask_normalization)
            for _, row, col in tree_tops_indices:
                mask_[_, row, col] = 1
            markers = ski.measure.label(mask_)

            markers_tree = ski.segmentation.expand_labels(
                markers,
                distance=max(math.ceil(params["tree_radius"]), 1),
            )
            labels = ski.segmentation.watershed(
                -out_image,
                markers,
                mask=markers_tree,
                watershed_line=True,
            )
            tree_area = labels.astype(bool)
            new_raster = np.ma.zeros_like(mask_normalization)
            new_raster[tree_area] = mask_normalization[tree_area]

            filtered_image = new_raster
        else:
            filtered_image = mask_normalization
            markers = np.ma.zeros_like(mask_normalization)
            tree_area = np.ma.zeros_like(mask_normalization, dtype=bool)
        filtered_image[filtered_image < 0.0] = 0.0
        if np.ma.is_masked(filtered_image):
            filtered_image.fill_value = default_nodata
        else:
            filtered_image = np.ma.masked_invalid(filtered_image)
            filtered_image.fill_value = default_nodata

        ras_nodata = default_nodata

        out_meta = src.meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "height": filtered_image.shape[1],
                "width": filtered_image.shape[2],
                "nodata": ras_nodata,
                "transform": out_transform,
            }
        )

    return filtered_image, out_meta, markers.squeeze(), tree_area.squeeze()
