"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This file hosts alternate CHM clipping/filtering logic for centerline runs.
"""

import math
import shapely as shp
import numpy as np
import rasterio
from rasterio import mask,features
import scipy.ndimage as ndimage
import skimage as ski

import beratools.core.constants as bt_const


def alt_clip_and_filter_regional_maxima_wgap(
        seedline_class,
        in_raster_file,
        clip_geom,
        buffer=1.0,
        default_nodata=bt_const.BT_NODATA,
    ):

    def erose_all_labels(labels_array):
        erose_array = np.zeros_like(labels_array)
        unique_labels = np.unique(labels_array)
        for label in unique_labels:
            if label == 0:
                continue  # Skip background

            # Create a binary mask for the current label
            mask = (labels_array == label)

            # Dilate the mask for this specific label
            erose_mask = ski.morphology.erosion(mask)

            # Assign the dilated mask back into the new array with the correct label value
            erose_array[erose_mask] = label

        return erose_array

    with rasterio.open(in_raster_file) as src:

        clip_geo_buffer = [shp.simplify(clip_geom,0.25).buffer(buffer)]
        out_image, out_transform = rasterio.mask.mask(src, clip_geo_buffer, crop=True)
        shapes = [(shp.simplify(clip_geom,0.25).buffer(buffer), 1)]  # Burn value '1' into the raster
        raster_array = features.rasterize(shapes,
            out_shape=out_image.shape[1:],
            transform=out_transform,
            fill=0,
            dtype=np.uint8,
            all_touched=True,

        )
        valid_area=raster_array==1
        valid_area=valid_area[np.newaxis,...]
        if src.nodata is not None:
            out_image[out_image == src.nodata] = 0.
            out_image[raster_array[np.newaxis,:] == 0] = default_nodata
        ras_nodata = src.meta["nodata"]
        cell_size = max(out_transform[0], -out_transform[4])
        if ras_nodata is None:
            ras_nodata = default_nodata

        #generate mask for valid raster data
        # data_mask = ~(np.ma.masked_equal(out_image, ras_nodata).mask)
        data_mask = valid_area
        #fill unmasked data with 0, otherwise keep the original value
        data_filled = np.where(data_mask, out_image, 0)
        data_filled = np.where(data_filled==ras_nodata,0, data_filled)


        #calulate the gaussian_filter's sigma to remove sharp noise without removing small crowns.
        sigma = math.ceil(seedline_class.tree_radius) * 0.5
        smoothed_data = ndimage.gaussian_filter(data_filled, sigma=sigma)
        #generate search tree crown footprint
        footprint = ski.morphology.disk(math.ceil(seedline_class.tree_radius))
        footprint = footprint.reshape(-1, footprint.shape[0], footprint.shape[1])

        smooth_mask = ndimage.gaussian_filter(data_mask.astype(float), sigma=sigma)
        mask_normalization = smoothed_data / smooth_mask
        mask_normalization[~data_mask] = np.nan
        mask_normalization = np.ma.masked_invalid(mask_normalization)
        tree_tops_indices = ski.feature.peak_local_max(
            mask_normalization,
            min_distance=1,  #find maximum number of tree tops
            exclude_border=False,
            num_peaks_per_label=1,
            footprint=footprint,
        )
        if len(tree_tops_indices) > 0:
            mask_ = np.ma.zeros_like(mask_normalization)
            for i, (_, row, col) in enumerate(tree_tops_indices):
                mask_[_, row, col] = 1
            markers = ski.measure.label(mask_)

            markers_tree = ski.segmentation.expand_labels(markers, distance=max(math.ceil(seedline_class.tree_radius), 1))
            markers_tree_=erose_all_labels(ski.segmentation.expand_labels(markers_tree,10))
            tree_area = markers_tree_.astype(bool)
            new_chm = np.ma.zeros_like(mask_normalization)
            new_chm[tree_area] = mask_normalization[tree_area]
            new_chm[~valid_area] = np.nan

            new_chm_gaps = np.ma.zeros_like(mask_normalization)
            new_chm_gaps=np.ma.where(markers_tree_==0,mask_normalization.data,0)
            new_chm_gaps = np.ma.where(mask_normalization.mask , 0, new_chm_gaps)

            filtered_image = new_chm

        else:
            filtered_image = mask_normalization  #
            markers = np.ma.zeros_like(mask_normalization)
            tree_area = np.ma.zeros_like(mask_normalization, dtype=bool)
        filtered_image[filtered_image < 0.0] = 0.0
        if np.ma.is_masked(filtered_image):
            filtered_image.fill_value = default_nodata
        else:
            filtered_image = np.ma.masked_invalid(filtered_image)
            filtered_image.fill_value = default_nodata

        ras_nodata = default_nodata

        # Update Metadata
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": filtered_image.shape[1],
            "width": filtered_image.shape[2],
            "nodata": ras_nodata,
            "transform": out_transform
        })

        tree_crown = ski.segmentation.watershed(-mask_normalization, markers, mask=~mask_normalization.mask,
                                                watershed_line=True)
        tree_crown_ = ski.morphology.erosion(tree_crown, footprint=ski.morphology.square(3)[np.newaxis,:] )
        tree_crown_area = tree_crown_.astype(bool)
        new_crown = np.ma.zeros_like(mask_normalization)
        new_crown[tree_crown_area] = mask_normalization[tree_crown_area]
        new_crown[~tree_crown_area] = 0.

    return filtered_image, out_meta,markers.squeeze(),tree_area.squeeze(), new_crown.squeeze(),new_chm_gaps.squeeze()
