"""Tests for cost-raster helpers."""

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import LineString

from beratools.core.algo_cost import reduce_chm_in_line_buffer


@pytest.mark.parametrize("add_band", [False, True])
def test_reduce_chm_in_line_buffer_preserves_source_and_mask(add_band):
    data = np.full((5, 5), 10.0)
    mask = np.zeros((5, 5), dtype=bool)
    data[2, 2] = -9999.0
    mask[2, 1] = True
    if add_band:
        data = data[np.newaxis, ...]
        mask = mask[np.newaxis, ...]

    source = np.ma.array(data, mask=mask, fill_value=-9999.0)
    source_before = source.copy()
    meta = {"transform": from_origin(0, 5, 1, 1), "nodata": -9999.0}
    line = LineString([(0.5, 2.5), (4.5, 2.5)])

    reduced = reduce_chm_in_line_buffer(source, meta, line, 0.49, 0.5)

    np.testing.assert_array_equal(source.data, source_before.data)
    np.testing.assert_array_equal(np.ma.getmaskarray(source), np.ma.getmaskarray(source_before))
    np.testing.assert_array_equal(np.ma.getmaskarray(reduced), mask)
    assert reduced.fill_value == -9999.0

    reduced_2d = reduced[0] if add_band else reduced
    assert np.all(reduced_2d.data[2, [0, 3, 4]] == 5.0)
    assert reduced_2d.mask[2, 1]
    assert reduced_2d.data[2, 2] == -9999.0
    assert np.all(reduced_2d.data[[0, 1, 3, 4], :] == 10.0)


@pytest.mark.parametrize(
    ("buffer_width", "multiplier", "message"),
    [
        (-1, 0.5, "buffer_width"),
        (1, -0.1, "multiplier"),
        (1, 1.1, "multiplier"),
    ],
)
def test_reduce_chm_in_line_buffer_validates_parameters(buffer_width, multiplier, message):
    source = np.ma.array(np.ones((2, 2)))
    meta = {"transform": from_origin(0, 2, 1, 1), "nodata": -9999.0}
    line = LineString([(0.5, 0.5), (1.5, 1.5)])

    with pytest.raises(ValueError, match=message):
        reduce_chm_in_line_buffer(source, meta, line, buffer_width, multiplier)
