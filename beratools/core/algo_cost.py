"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file hosts cost raster related functions.
"""

import numpy as np
import scipy
from rasterio.features import geometry_mask

import beratools.core.constants as bt_const


def reduce_chm_in_line_buffer(
    in_chm,
    meta,
    line,
    buffer_width,
    multiplier=0.5,
):
    """Return a CHM copy with valid values reduced inside a line buffer."""
    buffer_width = float(buffer_width)
    multiplier = float(multiplier)
    if buffer_width < 0.0:
        raise ValueError("buffer_width must be greater than or equal to zero")
    if not 0.0 <= multiplier <= 1.0:
        raise ValueError("multiplier must be between zero and one")
    if line is None or line.is_empty:
        raise ValueError("line must be a non-empty geometry")

    source = np.ma.asarray(in_chm)
    if source.ndim == 2:
        raster_shape = source.shape
    elif source.ndim == 3 and source.shape[0] == 1:
        raster_shape = source.shape[1:]
    else:
        raise ValueError("in_chm must be a 2D or single-band 3D raster")

    reduced = np.ma.array(source, dtype=float, copy=True)
    if buffer_width == 0.0 or multiplier == 1.0:
        return reduced

    inside_buffer = geometry_mask(
        [line.buffer(buffer_width)],
        out_shape=raster_shape,
        transform=meta["transform"],
        invert=True,
    )
    if reduced.ndim == 3:
        inside_buffer = inside_buffer[np.newaxis, ...]

    data = reduced.data
    valid = inside_buffer & ~np.ma.getmaskarray(reduced) & np.isfinite(data)
    nodata = meta.get("nodata")
    if nodata is not None and np.isfinite(nodata):
        valid &= data != nodata
    data[valid] *= multiplier
    return reduced


def cost_raster(
    in_raster,
    meta,
    tree_radius=2.5,
    canopy_ht_threshold=2.5,
    max_line_dist=2.5,
    canopy_avoid=0.4,
    cost_raster_exponent=1.5,
):
    """
    General version of cost_raster.

    To be merged later: variables and consistent nodata solution

    """
    if len(in_raster.shape) > 2:
        in_raster = np.squeeze(in_raster, axis=0)

    # regulate canopy_avoid between 0 and 1
    avoidance = max(0, min(1, canopy_avoid))
    cell_x, cell_y = meta["transform"][0], -meta["transform"][4]

    kernel_radius = int(tree_radius / cell_x)
    kernel = circle_kernel_refactor(2 * kernel_radius + 1, kernel_radius)
    dyn_canopy_ndarray = dyn_np_cc_map(in_raster, canopy_ht_threshold)

    cc_std, cc_mean = cost_focal_stats(dyn_canopy_ndarray, kernel)
    cc_smooth = cost_norm_dist_transform(dyn_canopy_ndarray, max_line_dist, [cell_x, cell_y])

    cost_clip = dyn_np_cost_raster_refactor(
        dyn_canopy_ndarray, cc_mean, cc_std, cc_smooth, avoidance, cost_raster_exponent
    )

    # TODO use nan or BT_DATA?
    cost_clip[in_raster == bt_const.BT_NODATA] = np.nan
    dyn_canopy_ndarray[in_raster == bt_const.BT_NODATA] = np.nan

    return cost_clip, dyn_canopy_ndarray


def remove_nan_from_array_refactor(matrix, replacement_value=bt_const.BT_NODATA_COST):
    # Use boolean indexing to replace nan values
    matrix[np.isnan(matrix)] = replacement_value


def dyn_np_cc_map(in_chm, canopy_ht_threshold):
    """
    Create a new canopy raster.

    MaskedArray based on the threshold comparison of in_chm (canopy height model)
    with canopy_ht_threshold. It assigns 1.0 where the condition is True (canopy)
    and 0.0 where the condition is False (non-canopy).

    """
    canopy_ndarray = np.ma.where(in_chm >= canopy_ht_threshold, 1.0, 0.0).astype(float)
    return canopy_ndarray


def cost_focal_stats(canopy_ndarray, kernel):
    mask = canopy_ndarray.mask if np.ma.is_masked(canopy_ndarray) else np.zeros(canopy_ndarray.shape, dtype=bool)
    # Replace masked/nan values with 0 for convolution; track valid pixel counts
    data = np.where(mask, 0.0, np.asarray(canopy_ndarray, dtype=float))
    valid = (~mask).astype(float)

    # Use fast C-level convolution instead of generic_filter with Python callbacks
    kernel_f = kernel.astype(float)
    sum_vals = scipy.ndimage.convolve(data, kernel_f, mode="nearest")
    count = scipy.ndimage.convolve(valid, kernel_f, mode="nearest")
    count = np.maximum(count, 1.0)  # avoid division by zero

    mean_array = sum_vals / count

    # Var = E[X^2] - E[X]^2
    sum_sq = scipy.ndimage.convolve(data * data, kernel_f, mode="nearest")
    variance = sum_sq / count - mean_array * mean_array
    variance = np.maximum(variance, 0.0)  # clamp numerical noise
    std_array = np.sqrt(variance)

    return std_array, mean_array


def cost_norm_dist_transform(canopy_ndarray, max_line_dist, sampling):
    """Compute a distance-based cost map based on the proximity of valid data points."""
    # Convert masked array to a regular array and fill the masked areas with np.nan
    in_ndarray = canopy_ndarray.filled(np.nan)

    # Compute the Euclidean distance transform (edt) where the valid values are
    euc_dist_array = scipy.ndimage.distance_transform_edt(
        np.logical_not(np.isnan(in_ndarray)), sampling=sampling
    )

    # Apply the mask back to set the distances to np.nan
    euc_dist_array[canopy_ndarray.mask] = np.nan

    # Calculate the smoothness (cost) array
    normalized_cost = float(max_line_dist) - euc_dist_array
    normalized_cost[normalized_cost <= 0.0] = 0.0
    smooth_cost_array = normalized_cost / float(max_line_dist)

    return smooth_cost_array


def dyn_np_cost_raster_refactor(canopy_ndarray, cc_mean, cc_std, cc_smooth, avoidance, cost_raster_exponent):
    # Calculate the lower and upper bounds for canopy cover (mean ± std deviation)
    lower_bound = cc_mean - cc_std
    upper_bound = cc_mean + cc_std

    # Calculate the ratio between the lower and upper bounds
    ratio_lower_upper = np.divide(
        lower_bound,
        upper_bound,
        where=upper_bound != 0,
        out=np.zeros(lower_bound.shape, dtype=float),
    )

    # Normalize the ratio to a scale between 0 and 1
    normalized_ratio = (1 + ratio_lower_upper) / 2

    # Adjust where the sum of mean and std deviation is less than or equal to zero
    adjusted_cover = cc_mean + cc_std
    adjusted_ratio = np.where(adjusted_cover <= 0, 0, normalized_ratio)

    # Combine canopy cover ratio with smoothing, weighted by avoidance factor
    weighted_cover = adjusted_ratio * (1 - avoidance) + (cc_smooth * avoidance)

    # Final cost modification based on canopy presence (masked by canopy_ndarray)
    final_cost = np.where(canopy_ndarray.data == 1, 1, weighted_cover)

    # Apply the exponential transformation to the cost values
    exponent_cost = np.exp(final_cost)

    # Raise the cost to the specified exponent
    result_cost_raster = np.power(exponent_cost, float(cost_raster_exponent))

    return result_cost_raster


def circle_kernel_refactor(size, radius):
    """
    Create a circular kernel using Scipy.

    Args:
    size : kernel size
    radius : radius of the circle

    Returns:
    kernel (ndarray): A circular kernel.

    Examples:
    kernel_scipy = create_circle_kernel_scipy(17, 8)
    will replicate xarray-spatial kernel
    cell_x = 0.3
    cell_y = 0.3
    tree_radius = 2.5
    convolution.circle_kernel(cell_x, cell_y, tree_radius)

    """
    # Create grid points (mesh)
    y, x = np.ogrid[:size, :size]

    # Center of the kernel
    center_x, center_y = (size - 1) / 2, (size - 1) / 2

    # Calculate the distance from the center
    distance = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)

    # Create a circular kernel
    kernel = distance <= radius
    return kernel.astype(float)
