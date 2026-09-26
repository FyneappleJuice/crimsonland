from __future__ import annotations

from grim.geom import Vec2

from .math_parity import f32, x87_pc24_add, x87_pc24_hypot, x87_pc24_mul, x87_pc24_sub

_NATIVE_FIND_SIZE_MARGIN_SCALE = f32(0.14285715)
_NATIVE_FIND_SIZE_MARGIN_BIAS = f32(3.0)


def native_find_size_margin(target_size: float) -> float:
    """Native collision threshold term used by `*_find_in_radius` routines."""

    return x87_pc24_add(
        x87_pc24_mul(f32(target_size), _NATIVE_FIND_SIZE_MARGIN_SCALE),
        _NATIVE_FIND_SIZE_MARGIN_BIAS,
    )


def within_native_find_radius(*, origin: Vec2, target: Vec2, radius: float, target_size: float) -> bool:
    """Evaluate the native strict ``*_find_in_radius`` predicate."""

    # Cheap reject before the exact x87 PC24 chain below (native_find_size_
    # margin included - its own x87 chain is deferred past this point too):
    # a candidate whose plain-double squared distance is already past
    # (radius + margin) by more than a full unit can't pass the exact check
    # either, however the per-op rounding falls - the x87-vs-host-double
    # discrepancy that test_within_native_find_radius_keeps_x87_pc24_boundary_
    # decisions pins is a small fraction of a unit, nowhere near this buffer.
    # Most candidates a dense spatial-hash cell (or a piercing bolt checking
    # many of them along its flight) returns are nowhere close to the
    # boundary, so this skips both x87 chains for them without changing any
    # result.
    plain_dx = float(target.x) - float(origin.x)
    plain_dy = float(target.y) - float(origin.y)
    approx_margin = float(target_size) * 0.14285715 + 3.0
    max_reach = float(radius) + approx_margin + 1.0
    if plain_dx * plain_dx + plain_dy * plain_dy > max_reach * max_reach:
        return False

    dx = x87_pc24_sub(f32(target.x), f32(origin.x))
    dy = x87_pc24_sub(f32(target.y), f32(origin.y))
    distance = x87_pc24_hypot(dx, dy)
    distance_outside_radius = x87_pc24_sub(distance, f32(radius))
    return distance_outside_radius < native_find_size_margin(float(target_size))


__all__ = ["native_find_size_margin", "within_native_find_radius"]
