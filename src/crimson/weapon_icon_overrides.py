from __future__ import annotations

"""Not native: per-weapon icon overrides (rewrite-only).

Some weapons' WEAPON_TABLE `icon_index` (weapons.py) just borrows another
weapon's frame from the shared UI_WICONS atlas as a placeholder - Evil Scythe
uses icon_index=25, Plasma Cannon's real slot. Checked at every site that
draws a weapon icon from that atlas, before falling back to the borrowed
frame, so replacing one doesn't need every call site rewritten by hand.
"""

from grim.assets import RuntimeResources, TextureId
from grim.raylib_api import rl

from .weapons import WeaponId

_OVERRIDE_TEXTURE_BY_WEAPON: dict[WeaponId, TextureId] = {
    WeaponId.EVIL_SCYTHE: TextureId.EVIL_SCYTHE_WEAPON_ICON,
}

# Per-weapon size multiplier for override art that reads big/small at the
# standard weapon-icon slot size (1.0 = no change).
_ICON_SIZE_MULT_BY_WEAPON: dict[WeaponId, float] = {
    WeaponId.EVIL_SCYTHE: 0.8,
}


def weapon_icon_override_texture(resources: RuntimeResources, weapon_id: int) -> rl.Texture | None:
    """The dedicated icon texture for `weapon_id`, or None to keep using the
    shared UI_WICONS atlas frame (Weapon.icon_index) as before."""
    texture_id = _OVERRIDE_TEXTURE_BY_WEAPON.get(WeaponId(weapon_id))
    if texture_id is None:
        return None
    return resources.texture_optional(texture_id)


def weapon_icon_size_mult(weapon_id: int) -> float:
    """Per-weapon size multiplier for override art (1.0 = no change) - for
    call sites that draw centred-on-a-point rather than from a top-left dst
    rect, where weapon_icon_dst_rect doesn't apply."""
    return _ICON_SIZE_MULT_BY_WEAPON.get(WeaponId(weapon_id), 1.0)


def weapon_icon_dst_rect(dst: rl.Rectangle, weapon_id: int) -> rl.Rectangle:
    """`dst` (a top-left-anchored draw rect) shrunk toward its own centre by
    that weapon's _ICON_SIZE_MULT_BY_WEAPON entry - unchanged if it has none."""
    mult = weapon_icon_size_mult(weapon_id)
    if mult == 1.0:
        return dst
    new_w = dst.width * mult
    new_h = dst.height * mult
    return rl.Rectangle(
        dst.x + (dst.width - new_w) * 0.5,
        dst.y + (dst.height - new_h) * 0.5,
        new_w,
        new_h,
    )


__all__ = ["weapon_icon_dst_rect", "weapon_icon_override_texture", "weapon_icon_size_mult"]
