"""Shared helpers for converting meter-based parameters to CRS-native units."""

import pyproj
import shapely.ops as sh_ops


def require_crs(gdf_or_crs, parameter_label):
    """Return a normalized pyproj CRS or raise if unavailable."""
    candidate = getattr(gdf_or_crs, "crs", gdf_or_crs)
    crs = pyproj.CRS.from_user_input(candidate) if candidate else None
    if crs is None:
        raise ValueError(f"Input line CRS is missing; cannot apply '{parameter_label}'.")
    return crs


def build_linear_unit_context(crs, reference_geom):
    """Build conversion context between meters and source CRS units."""
    if crs.is_geographic:
        if reference_geom is None or reference_geom.is_empty:
            raise ValueError("Unable to determine reference geometry for geographic CRS unit conversion.")
        ref_point = reference_geom.representative_point()
        metric_crs = pyproj.CRS.from_proj4(
            f"+proj=aeqd +lat_0={ref_point.y} +lon_0={ref_point.x} +datum=WGS84 +units=m +no_defs"
        )
        to_metric = pyproj.Transformer.from_crs(crs, metric_crs, always_xy=True)
        to_source = pyproj.Transformer.from_crs(metric_crs, crs, always_xy=True)
        return {
            "is_geographic": True,
            "to_metric": to_metric,
            "to_source": to_source,
            "unit_factor": None,
        }

    unit_factor = crs.axis_info[0].unit_conversion_factor if crs.axis_info else None
    if unit_factor is None or unit_factor <= 0:
        raise ValueError("Unable to determine projected CRS linear units.")
    return {
        "is_geographic": False,
        "to_metric": None,
        "to_source": None,
        "unit_factor": unit_factor,
    }


def meters_to_native_units(distance_m, unit_ctx):
    """Convert distance from meters to source CRS units."""
    if unit_ctx["is_geographic"]:
        return float(distance_m)
    return float(distance_m) / float(unit_ctx["unit_factor"])


def geometry_length_meters(geom, unit_ctx):
    """Measure geometry length in meters under the provided unit context."""
    if geom is None or geom.is_empty:
        return 0.0
    if unit_ctx["is_geographic"]:
        geom_metric = sh_ops.transform(unit_ctx["to_metric"].transform, geom)
        return float(geom_metric.length)
    return float(geom.length) * float(unit_ctx["unit_factor"])


def convert_meters_param(
    gdf_or_crs,
    value_m,
    parameter_label,
    reference_geom=None,
    allow_geographic=False,
    min_value=None,
):
    """Convert a meter-based parameter value to source CRS units."""
    crs = require_crs(gdf_or_crs, parameter_label)
    if reference_geom is None and hasattr(gdf_or_crs, "empty"):
        reference_geom = None if gdf_or_crs.empty else gdf_or_crs.unary_union.envelope

    unit_ctx = build_linear_unit_context(crs, reference_geom)
    if unit_ctx["is_geographic"] and not allow_geographic:
        raise ValueError(f"{parameter_label} requires a projected CRS.")

    value_native = meters_to_native_units(float(value_m), unit_ctx)
    if min_value is not None:
        value_native = max(float(min_value), float(value_native))
    return float(value_native)


def convert_meters_param_projected(
    gdf_or_crs,
    value_m,
    parameter_label,
    reference_geom=None,
    min_value=None,
):
    """Convert a meter-based parameter that requires projected CRS units."""
    crs = require_crs(gdf_or_crs, parameter_label)
    if crs.is_geographic:
        raise ValueError(f"{parameter_label} requires a projected CRS.")
    return convert_meters_param(
        crs,
        value_m,
        parameter_label,
        reference_geom=reference_geom,
        allow_geographic=False,
        min_value=min_value,
    )


def convert_meters_param_projected_from_osr(
    osr_crs,
    value_m,
    parameter_label,
    min_value=None,
):
    """Convert a meter parameter using an OSR CRS object or CRS text."""
    crs_input = osr_crs.ExportToWkt() if hasattr(osr_crs, "ExportToWkt") else osr_crs
    return convert_meters_param_projected(
        crs_input,
        value_m,
        parameter_label,
        min_value=min_value,
    )
