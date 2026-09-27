from __future__ import annotations

from crimson.gameplay import GameplayState
from crimson.meta import relics as relics_module
from crimson.perks.ids import PerkId
from crimson.run_mods.ids import RunModId
from crimson.sim.state_types import PlayerState
from crimson.ui.sandbox_debug_panel import (
    SandboxDebugPanel,
    _TAB_PERKS,
    _TAB_RELICS,
    _TAB_RUN_MODS,
    _TAB_WEAPONS,
)
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _players() -> list[PlayerState]:
    return [PlayerState(index=0, pos=Vec2())]


def test_add_and_remove_a_perk_round_trips_the_count() -> None:
    panel = SandboxDebugPanel()
    panel.tab = _TAB_PERKS
    players = _players()
    state = GameplayState()

    panel._add(int(PerkId.BLOODY_MESS_QUICK_LEARNER), players=players, state=state, creatures=[])
    assert players[0].perk_counts[int(PerkId.BLOODY_MESS_QUICK_LEARNER)] == 1

    panel._remove(int(PerkId.BLOODY_MESS_QUICK_LEARNER), players=players, state=state)
    assert players[0].perk_counts[int(PerkId.BLOODY_MESS_QUICK_LEARNER)] == 0


def test_remove_never_takes_a_perk_count_below_zero() -> None:
    panel = SandboxDebugPanel()
    panel.tab = _TAB_PERKS
    players = _players()

    panel._remove(int(PerkId.BLOODY_MESS_QUICK_LEARNER), players=players, state=GameplayState())
    assert players[0].perk_counts[int(PerkId.BLOODY_MESS_QUICK_LEARNER)] == 0


def test_add_and_remove_a_run_mod_round_trips_the_count() -> None:
    panel = SandboxDebugPanel()
    panel.tab = _TAB_RUN_MODS
    players = _players()
    run_mod_id = int(next(iter(RunModId)))

    panel._add(run_mod_id, players=players, state=GameplayState(), creatures=[])
    assert players[0].run_mod_counts[run_mod_id] == 1

    panel._remove(run_mod_id, players=players, state=GameplayState())
    assert players[0].run_mod_counts[run_mod_id] == 0


def test_add_and_remove_a_relic_updates_active_relics_and_stat_mods() -> None:
    panel = SandboxDebugPanel()
    panel.tab = _TAB_RELICS
    players = _players()
    relic_id = int(next(iter(relics_module.RelicId)))

    try:
        panel._add(relic_id, players=players, state=GameplayState(), creatures=[])
        assert relic_id in panel.active_relic_ids
        assert relic_id in relics_module.active_relic_ids()

        panel._remove(relic_id, players=players, state=GameplayState())
        assert relic_id not in panel.active_relic_ids
        assert relic_id not in relics_module.active_relic_ids()
    finally:
        # Session-global state - don't leak into other tests.
        relics_module.end_run()


def test_weapon_tab_equips_a_weapon_and_reset_returns_to_pistol() -> None:
    panel = SandboxDebugPanel()
    panel.tab = _TAB_WEAPONS
    players = _players()
    state = GameplayState()

    panel._add(int(WeaponId.ASSAULT_RIFLE), players=players, state=state, creatures=[])
    assert players[0].weapon.weapon_id == WeaponId.ASSAULT_RIFLE

    panel._remove(int(WeaponId.ASSAULT_RIFLE), players=players, state=state)
    assert players[0].weapon.weapon_id == WeaponId.PISTOL


def test_relic_debug_activation_never_touches_the_persistent_inventory(tmp_path, monkeypatch) -> None:
    # The debug panel must not award/save relics to disk - it's a session-only
    # toggle, unlike a real monster drop.
    relics_module.init_relics(tmp_path)
    before_owned = list(relics_module.relic_state().owned)
    before_placements = list(relics_module.relic_state().placements)

    panel = SandboxDebugPanel()
    panel.tab = _TAB_RELICS
    relic_id = int(next(iter(relics_module.RelicId)))
    try:
        panel._add(relic_id, players=_players(), state=GameplayState(), creatures=[])
        assert relics_module.relic_state().owned == before_owned
        assert relics_module.relic_state().placements == before_placements
    finally:
        relics_module.end_run()
