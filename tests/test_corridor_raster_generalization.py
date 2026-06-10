import numpy as np

from beratools.core import algo_common


def test_corridor_threshold_to_mask_uses_zero_as_inside_corridor():
    corridor_thresh = np.array(
        [
            [0.0, 1.0],
            [1.0, 0.0],
        ]
    )

    mask = algo_common.corridor_threshold_to_mask(corridor_thresh)

    np.testing.assert_array_equal(mask, np.array([[1, 0], [0, 1]], dtype=np.int32))


def test_apply_canopy_mask_keeps_only_corridor_cells_with_zero_canopy():
    corridor_mask = np.array(
        [
            [1, 1],
            [0, 1],
        ],
        dtype=np.int32,
    )
    canopy_raster = np.array(
        [
            [0, 1],
            [0, 0],
        ],
        dtype=np.int32,
    )

    mask = algo_common.apply_canopy_mask(corridor_mask, canopy_raster)

    np.testing.assert_array_equal(mask, np.array([[1, 0], [0, 1]], dtype=np.int32))


def test_generalize_binary_mask_expand_shrink_is_cell_based():
    mask = np.zeros((5, 5), dtype=np.int32)
    mask[1:4, 1:4] = 1
    mask[2, 2] = 0

    generalized = algo_common.generalize_binary_mask(mask, exp_shk_cell=1, boundary_clean=False)

    assert generalized[2, 2] == 1


def test_generalize_binary_mask_boundary_clean_is_not_noop():
    mask = np.ones((3, 3), dtype=np.int32)
    mask[1, 1] = 0

    generalized = algo_common.generalize_binary_mask(mask, exp_shk_cell=0, boundary_clean=True)

    assert generalized[1, 1] == 1


def test_morph_raster_wraps_corridor_canopy_and_generalization():
    corridor_thresh = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ]
    )
    canopy_raster = np.zeros((3, 3), dtype=np.int32)

    clean = algo_common.morph_raster(corridor_thresh, canopy_raster, exp_shk_cell=0, cell_size_x=2.0)

    assert clean[1, 1] == 0
