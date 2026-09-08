from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import crimson.render.world.player_status as ps
from crimson.bonuses.hud import BonusHudState
from crimson.bonuses.ids import BonusId
from grim.geom import Vec2


class _Tex:
    width = 256
    height = 256


def _ctx(bonus_hud: BonusHudState):
    resources = SimpleNamespace(small_font=None, texture=lambda _id: cast("object", _Tex()))
    frame = SimpleNamespace(state=SimpleNamespace(bonus_hud=bonus_hud), resources=resources)
    return cast("ps.WorldRenderCtx", SimpleNamespace(frame=frame))


def _activate(hud: BonusHudState, rows: list[tuple[BonusId, int, float]]) -> None:
    for slot, (bonus_id, icon_id, timer) in zip(hud.slots, rows, strict=False):
        slot.active = True
        slot.bonus_id = bonus_id
        slot.icon_id = icon_id
        slot.timer_value = timer


def test_powerups_stack_upward_fifo_oldest_nearest_player(mocker) -> None:
    draw_texture_pro = mocker.patch.object(ps.rl, "draw_texture_pro")
    mocker.patch.object(ps.rl, "draw_rectangle")

    hud = BonusHudState()
    _activate(
        hud,
        [
            (BonusId.WEAPON_POWER_UP, 4, 10.0),  # oldest
            (BonusId.SHIELD, 10, 6.0),
            (BonusId.SPEED, 13, 2.4),  # newest
        ],
    )

    ps._draw_player_powerups(_ctx(hud), screen=Vec2(400.0, 300.0), scale=1.0, r_out=22.5, alpha=1.0)

    ys = [call.args[2].y for call in draw_texture_pro.call_args_list]
    assert len(ys) == 3
    # Oldest drawn lowest (largest y, nearest the player); each newer one higher.
    assert ys[0] > ys[1] > ys[2]


def test_powerups_skip_inactive_and_expired(mocker) -> None:
    draw_texture_pro = mocker.patch.object(ps.rl, "draw_texture_pro")
    mocker.patch.object(ps.rl, "draw_rectangle")

    hud = BonusHudState()
    _activate(hud, [(BonusId.WEAPON_POWER_UP, 4, 5.0)])
    hud.slots[1].active = True
    hud.slots[1].icon_id = 10
    hud.slots[1].timer_value = 0.0  # expired

    ps._draw_player_powerups(_ctx(hud), screen=Vec2(0.0, 0.0), scale=1.0, r_out=22.5, alpha=1.0)
    assert draw_texture_pro.call_count == 1


def test_powerups_noop_when_none_active(mocker) -> None:
    draw_texture_pro = mocker.patch.object(ps.rl, "draw_texture_pro")
    ps._draw_player_powerups(_ctx(BonusHudState()), screen=Vec2(0.0, 0.0), scale=1.0, r_out=22.5, alpha=1.0)
    draw_texture_pro.assert_not_called()


def test_fork_icon_is_procedural_and_blade_icon_uses_the_projs_atlas(mocker) -> None:
    mocker.patch.object(ps.rl, "draw_rectangle")
    mocker.patch.object(ps.rl, "draw_texture_pro")
    fork = mocker.patch.object(ps, "draw_fork_icon")
    blade = mocker.patch.object(ps, "draw_blade_icon")

    hud = BonusHudState()
    _activate(hud, [(BonusId.PROJECTILE_FORK, 15, 8.0), (BonusId.BLADE, 3, 5.0)])

    ps._draw_player_powerups(_ctx(hud), screen=Vec2(300.0, 300.0), scale=1.0, r_out=22.5, alpha=1.0)

    fork.assert_called_once()
    blade.assert_called_once()
