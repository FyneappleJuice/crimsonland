from __future__ import annotations

import pytest

from crimson.creatures.runtime import CreatureAiMode, CreaturePool
from crimson.creatures.spawn import CreatureInit
from crimson.gameplay import GameplayState, player_update
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import turret
from crimson.perks import PerkId
from crimson.perks.runtime.apply import perk_apply
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import weapon_assign_player
from crimson.weapon_runtime import crit as crit_module
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def _never_crit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 1.0)


def _pistol_player() -> PlayerState:
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=GameplayState())
    return player


def _build_turret(state: GameplayState, pool: CreaturePool, player: PlayerState) -> int:
    """Drives player_update through a full build cycle and returns the
    spawned turret's creature index (always the last entry appended to
    turret_indices - pool slot numbers can be reused after an eviction, so
    diffing against the prior list isn't reliable)."""
    before_count = len(player.turret_indices)
    player_update(
        player,
        PlayerInput(reload_pressed=True),
        dt=0.001,
        state=state,
        creatures=pool.entries,
        creature_pool=pool,
    )
    assert player.turret_relic_building
    duration = float(player.turret_build_duration)
    assert duration > 0.0
    player_update(
        player,
        PlayerInput(),
        dt=duration + 0.1,
        state=state,
        creatures=pool.entries,
        creature_pool=pool,
    )
    assert len(player.turret_indices) == min(before_count + 1, turret.TURRET_RELIC_MAX_PER_PLAYER)
    return player.turret_indices[-1]


def test_relic_inactive_by_default() -> None:
    player = _pistol_player()
    assert not turret.turret_relic_active()
    assert turret.can_fire_own_weapon(player)


def test_player_cannot_fire_while_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    player = _pistol_player()
    before_ammo = float(player.weapon.ammo)
    for _ in range(10):
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=1.0 / 60.0, state=state)
    assert float(player.weapon.ammo) == before_ammo
    assert not any(p.active for p in state.projectiles.entries)


def test_reload_press_starts_a_build_with_the_right_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    player = _pistol_player()

    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)

    assert player.turret_relic_building
    # Pistol's own reload_time (1.2s, per Pact of the Giant's test comments), x5.
    assert player.turret_build_duration == pytest.approx(1.2 * turret.TURRET_BUILD_DURATION_MULT, rel=1e-3)
    assert player.turret_build_timer == pytest.approx(player.turret_build_duration)
    # The player's own weapon must never show (or actually run) a reload -
    # only the build timer drives anything visible.
    assert not player.weapon.reload_active
    assert player.weapon.reload_timer == 0.0


def test_reload_press_again_cancels_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    player = _pistol_player()

    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)
    assert player.turret_relic_building

    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)
    assert not player.turret_relic_building
    assert player.turret_build_timer == 0.0


def test_reload_press_still_flips_giant_pacts_active_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Turret's own Reload-key handling always wins priority over
    # Pact of the Giant's (gameplay.py's reload-key branch), so Giant Pact's
    # own start_combined_reload+flip_active_slot never runs while Turret is
    # equipped - but the player should still be able to redirect which slot
    # a floor weapon pickup replaces, the one piece of that behavior that
    # still matters when they can't fire at all.
    from crimson.weapon_runtime import init_default_alt_weapon

    _equip(monkeypatch, RelicId.TURRET_LOW, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    player = _pistol_player()
    init_default_alt_weapon(player)
    assert player.giant_pact_active_slot == 0

    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)
    assert player.giant_pact_active_slot == 1

    # Cancelling the build (second press) still flips it too - every Reload
    # press flips, matching Giant Pact's own convention.
    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)
    assert player.giant_pact_active_slot == 0


def test_player_is_rooted_while_building(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    player = _pistol_player()
    player.pos = Vec2(500.0, 500.0)

    player_update(player, PlayerInput(reload_pressed=True), dt=0.001, state=state)
    assert player.turret_relic_building

    start = Vec2(player.pos.x, player.pos.y)
    for _ in range(30):
        player_update(
            player,
            PlayerInput(move=Vec2(1.0, 0.0), aim=Vec2(600.0, 500.0)),
            dt=1.0 / 60.0,
            state=state,
        )
    assert player.pos.x == pytest.approx(start.x, abs=1e-6)
    assert player.pos.y == pytest.approx(start.y, abs=1e-6)


def test_build_completes_and_spawns_a_turret_in_front_of_the_player(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.pos = Vec2(500.0, 500.0)
    player.aim_heading = 0.0

    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]

    assert entry.active
    assert entry.is_turret
    assert entry.ai_mode == CreatureAiMode.HOLD_TIMER
    assert entry.move_speed == 0.0
    assert entry.turret_owner_player_index == 0
    assert entry.turret_weapon is not None
    assert entry.pos.distance_to(player.pos) == pytest.approx(turret.TURRET_SPAWN_OFFSET, rel=1e-3)


def test_third_build_evicts_the_oldest_turret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pool slot numbers can be reused after an eviction (the evicted slot is
    # the first one freed, so a fresh spawn_init() may reclaim it) - assert on
    # the FIFO ordering of turret_indices and the total live-turret count,
    # not on any one build's slot number still being inactive.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()

    _build_turret(state, pool, player)
    second = _build_turret(state, pool, player)
    third = _build_turret(state, pool, player)

    assert player.turret_indices == [second, third]
    assert sum(1 for c in pool.entries if c.active and c.is_turret) == turret.TURRET_RELIC_MAX_PER_PLAYER


def test_turret_inherits_live_stats_granted_after_it_was_built(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    pool.spawn_init(
        CreatureInit(
            origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0,
        ),
    )
    creatures = pool.entries

    # Fastshot (perk) granted only *after* the turret already exists.
    perk_apply(state, [player], PerkId.FASTSHOT)
    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0)

    assert float(player.stats.shot_cooldown_mult) < 1.0
    assert entry.turret_weapon is not None


def test_turret_shot_seq_advances_across_shots(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Seeker Rounds ("Fire and Forget") dedupes hits by shot_seq,
    # which used to only ever mutate the throwaway shooter clone - every
    # turret shot stamped the same (never-advancing) value, so the dedup
    # check could never see a "new" shot after the first and the hit counter
    # got permanently stuck.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.turret_weapon.ammo = 1000.0
    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    seen_seq: set[int] = set()
    for _ in range(300):
        turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)
        seen_seq.add(int(entry.turret_shot_seq))

    assert len(seen_seq) > 1, "turret_shot_seq never advanced across shots"


def test_turret_pendulum_phase_flips_on_its_own_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Pendulum's phase flip used to only ever mutate the
    # throwaway shooter clone (gameplay.py's clear_reload_active_if_gate_open),
    # so a turret's phase was permanently stuck at whatever the real player's
    # own (frozen, since they can't fire) phase happened to be.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.perk_counts[int(PerkId.PENDULUM)] = 1
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.turret_weapon.ammo = 2.0  # force a reload after a couple of shots
    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    start_phase = entry.turret_pendulum_phase
    for _ in range(600):
        turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)
        if entry.turret_pendulum_phase != start_phase:
            break
    else:
        pytest.fail("turret's own Pendulum phase never flipped")


def test_turret_does_not_pay_giant_pacts_dual_wield_tax(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Pact of the Giant's 1.5x fire-rate tax (fire_rate_cost_mult)
    # is gated only on the relic being equipped, not on actually
    # dual-wielding - a real player never hits this gap (their alt slot is
    # always seeded whenever the relic is active), but a turret's shooter
    # always has alt_weapon=None, so it would otherwise eat the tax for a
    # second weapon it can never fire.
    _equip(monkeypatch, RelicId.TURRET_LOW, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]

    target_idx = pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    from crimson.weapon_runtime import WeaponFireCtx, fire_weapon

    solo_state = GameplayState()
    solo_player = _pistol_player()
    solo_player.pos = Vec2(entry.pos.x, entry.pos.y)
    solo_player.aim = creatures[target_idx].pos
    solo_player.aim_heading = 0.0
    fire_weapon(
        WeaponFireCtx(
            player=solo_player,
            input_state=PlayerInput(aim=solo_player.aim, fire_down=True),
            dt=1.0,
            state=solo_state,
            # True un-taxed baseline: this bare PlayerState has no alt_weapon
            # either, so without this it would *also* incorrectly eat Giant
            # Pact's tax (same gap this test exists to catch) and the
            # comparison would be tautological.
            giant_pact_partner_dry=True,
        ),
    )
    solo_cooldown = float(solo_player.weapon.shot_cooldown)

    for _ in range(120):
        turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)
        if any(p.active for p in state.projectiles.entries):
            break

    assert float(entry.turret_weapon.shot_cooldown_max) == pytest.approx(solo_cooldown, rel=1e-3)


def test_turret_dual_wields_when_player_actually_does(monkeypatch: pytest.MonkeyPatch) -> None:
    # A player who is genuinely dual-wielding (Pact of the Giant + a real alt
    # weapon) should have their turret dual-wield too - its own persistent
    # alt WeaponSlot, alternating fire through giant_pact_dual_fire exactly
    # like the player/Hollow Form do.
    from crimson.weapon_runtime import init_default_alt_weapon

    _equip(monkeypatch, RelicId.TURRET_LOW, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    init_default_alt_weapon(player)
    assert player.alt_weapon is not None
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    assert entry.turret_alt_weapon is None  # not yet synced - first tick does it

    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    primary_shots = 0
    alt_shots = 0
    for _ in range(600):
        before_primary = float(entry.turret_weapon.ammo) if entry.turret_weapon else 0.0
        before_alt = float(entry.turret_alt_weapon.ammo) if entry.turret_alt_weapon else None
        turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)
        if entry.turret_alt_weapon is not None:
            if float(entry.turret_weapon.ammo) < before_primary:
                primary_shots += 1
            if before_alt is not None and float(entry.turret_alt_weapon.ammo) < before_alt:
                alt_shots += 1

    assert entry.turret_alt_weapon is not None
    assert entry.turret_alt_weapon.weapon_id == player.alt_weapon.weapon_id
    assert primary_shots > 0
    assert alt_shots > 0, "turret's alt weapon slot never fired - not actually dual-wielding"


def test_turret_damage_penalty_only_no_rate_or_reload_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]

    target_idx = pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    # Solo baseline: a plain player firing the same weapon at the same range.
    solo_state = GameplayState()
    solo_player = _pistol_player()
    solo_player.pos = Vec2(entry.pos.x, entry.pos.y)
    from crimson.weapon_runtime import WeaponFireCtx, fire_weapon

    solo_player.aim = creatures[target_idx].pos
    solo_player.aim_heading = 0.0
    fire_weapon(
        WeaponFireCtx(
            player=solo_player,
            input_state=PlayerInput(aim=solo_player.aim, fire_down=True),
            dt=1.0,
            state=solo_state,
        ),
    )
    solo_shot = next(p for p in solo_state.projectiles.entries if p.active)
    solo_cooldown = float(solo_player.weapon.shot_cooldown)

    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)
    fired = [p for p in state.projectiles.entries if p.active]
    assert fired, "turret never fired"
    turret_shot = fired[0]

    assert float(turret_shot.crit_mult) == pytest.approx(float(solo_shot.crit_mult) * turret.TURRET_DAMAGE_MULT)
    assert turret_shot.owner.via_turret is True
    # No fire-rate penalty: the turret's post-shot cooldown matches the
    # player's own solo shot exactly.
    assert float(entry.turret_weapon.shot_cooldown_max) == pytest.approx(solo_cooldown, rel=1e-3)


def test_turret_leech_hit_heals_both_turret_and_player(monkeypatch: pytest.MonkeyPatch) -> None:
    # A turret's own hit builds a leech instance for itself (heals its own
    # hp) IN ADDITION TO the real player's own instance (already-safe
    # behavior) - per the owner's explicit call that both benefit.
    from crimson.creatures.damage_types import CreatureDamageType
    from crimson.effects import FxQueue, FxQueueRotated
    from crimson.game_modes import GameMode
    from crimson.owner_ref import OwnerRef
    from crimson.sim.world_state import WorldState

    _equip(monkeypatch, RelicId.TURRET_LOW, RelicId.LEECH_LOW)
    world = WorldState.build(world_size=1024.0, demo_mode_active=True, hardcore=False, quest_fail_retry_count=0)
    world.players.append(_pistol_player())
    player = world.players[0]
    idx = _build_turret(world.state, world.creatures, player)
    entry = world.creatures.entries[idx]
    entry.hp = 50.0  # below max so the heal is visible

    victim_idx = world.creatures.spawn_init(
        CreatureInit(
            origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0,
            health=1000.0, max_health=1000.0,
        ),
    )

    def _fake_projectile_step(*args: object, **kwargs: object) -> list:
        from typing import cast

        from crimson.projectiles.runtime import PrimaryStepCtx

        ctx = cast(PrimaryStepCtx, args[0])
        runtime = ctx.options.creature_damage_runtime
        assert runtime is not None
        import msgspec

        owner = msgspec.structs.replace(OwnerRef.from_player(0), via_turret=True, turret_creature_index=idx)
        runtime.apply_creature_damage(victim_idx, 100.0, int(CreatureDamageType.BULLET), Vec2(), owner)
        return []

    monkeypatch.setattr(world.state.projectiles, "step", _fake_projectile_step)
    world.step(
        0.016,
        inputs=None,
        world_size=1024.0,
        damage_scale_by_type={},
        detail_preset=5,
        fx_queue=FxQueue(),
        fx_queue_rotated=FxQueueRotated(),
        game_mode=GameMode.SURVIVAL,
        perk_progression_enabled=False,
    )

    assert world.creatures.entries[idx].turret_leech_pending_heal
    assert player.leech_pending_heal


def test_turret_kill_costs_both_turret_and_player_hp(monkeypatch: pytest.MonkeyPatch) -> None:
    # A turret's own kill costs that turret's own hp IN ADDITION TO the real
    # player's current-HP percentage (already-safe behavior) - per the
    # owner's explicit call that both pay.
    from crimson.creatures.damage import creature_apply_damage_with_lethal_followup
    from crimson.creatures.damage_types import CreatureDamageType
    from crimson.creatures.runtime import _CreaturePoolCreatureDamageRuntime
    from crimson.owner_ref import OwnerRef
    from grim.rand import Crand

    from crimson.weapon_runtime.availability import prepare_weapon_availability

    _equip(monkeypatch, RelicId.TURRET_LOW, RelicId.LEECH_LOW)
    state = GameplayState()
    prepare_weapon_availability(state)
    pool = CreaturePool()
    player = _pistol_player()
    player.health = 100.0
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    turret_hp_before = float(entry.hp)

    victim_idx = pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    victim = pool.entries[victim_idx]

    runtime = _CreaturePoolCreatureDamageRuntime(
        pool=pool, state=state, players=[player], rng=Crand(1), dt=0.016,
        detail_preset=5, world_width=1024.0, world_height=1024.0, fx_queue=None, deaths=[], sfx=[],
    )
    owner = OwnerRef.from_player(0)
    import msgspec

    owner = msgspec.structs.replace(owner, via_turret=True, turret_creature_index=idx)
    creature_apply_damage_with_lethal_followup(
        victim, creature_index=victim_idx, damage_amount=float(victim.hp) + 10.0,
        damage_type=int(CreatureDamageType.BULLET), impulse=Vec2(),
        owner=owner, dt=0.016, players=[player], rng=Crand(1),
        creature_damage_runtime=runtime,
    )

    assert float(pool.entries[idx].hp) < turret_hp_before
    assert player.health < 100.0


def test_turret_fires_immediately_even_while_still_turning(monkeypatch: pytest.MonkeyPatch) -> None:
    # The turret holds its trigger down the whole time it has a target,
    # simulating a held LMB, rather than waiting to be perfectly aligned.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.heading = float(entry.heading) + 3.0  # facing well away from the target

    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 40.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=1.0 / 60.0)

    assert any(p.active for p in state.projectiles.entries)


def test_turret_turn_rate_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.heading = 0.0

    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x, entry.pos.y - 100.0), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries
    dt = 1.0 / 60.0

    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=creatures, dt=dt)

    assert abs(float(entry.heading)) <= turret.TURRET_TURN_RATE_RAD_S * dt + 1e-6


def test_turret_targets_the_nearest_within_override_radius(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]

    near_idx = pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 50.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    pool.spawn_init(
        CreatureInit(origin_template_id=0, pos=Vec2(entry.pos.x + 200.0, entry.pos.y), heading=0.0, phase_seed=0),
    )
    creatures = pool.entries

    for _ in range(50):
        picked = turret._select_turret_target(entry.pos, creatures, max_range=turret.TURRET_DEFAULT_RANGE)
        assert picked is not None
        assert picked[0] == near_idx


def test_creature_contact_damages_turret_hp_not_player_health(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.health = 100.0
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    before_hp = float(entry.hp)

    biter_idx = pool.spawn_init(
        CreatureInit(
            origin_template_id=0, pos=Vec2(entry.pos.x + 5.0, entry.pos.y), heading=0.0, phase_seed=0,
            health=100.0, max_health=100.0, contact_damage=10.0, size=50.0,
        ),
    )

    from crimson.creatures.runtime import _apply_turret_contact_damage

    _apply_turret_contact_damage(pool.entries, state=state, dt=1.0 / 60.0)

    assert float(pool.entries[idx].hp) == pytest.approx(before_hp - 10.0)
    assert player.health == 100.0
    assert float(pool.entries[biter_idx].attack_cooldown) > 0.0


def test_turret_death_prunes_indices_and_grants_no_xp(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.experience = 0
    idx = _build_turret(state, pool, player)

    from crimson.creatures.damage import creature_apply_damage_with_lethal_followup
    from crimson.creatures.damage_types import CreatureDamageType
    from crimson.creatures.runtime import _CreaturePoolCreatureDamageRuntime
    from crimson.owner_ref import OwnerRef
    from grim.rand import Crand

    runtime = _CreaturePoolCreatureDamageRuntime(
        pool=pool, state=state, players=[player], rng=Crand(1), dt=0.016,
        detail_preset=5, world_width=1024.0, world_height=1024.0, fx_queue=None, deaths=[], sfx=[],
    )
    entry = pool.entries[idx]
    # A creature-owned hit, not a player-owned one - turrets are now immune
    # to all player-sourced damage (this is how a turret actually dies in
    # practice: creature bite contact, never a player/turret shot).
    creature_apply_damage_with_lethal_followup(
        entry, creature_index=idx, damage_amount=float(entry.hp) + 10.0,
        damage_type=int(CreatureDamageType.BULLET), impulse=Vec2(),
        owner=OwnerRef.from_creature(99), dt=0.016, players=[player], rng=Crand(1),
        creature_damage_runtime=runtime,
    )

    assert idx not in player.turret_indices
    assert player.experience == 0


def test_player_owned_damage_never_hits_a_turret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: turrets are a plain CreatureState with no faction concept,
    # so every player-sourced damage path (including the turret's own shots,
    # attributed to the owning player) treated them like an ordinary hostile
    # monster and damaged them - see world_state.py's apply_creature_damage.
    from crimson.creatures.damage_types import CreatureDamageType
    from crimson.effects import FxQueue, FxQueueRotated
    from crimson.game_modes import GameMode
    from crimson.owner_ref import OwnerRef
    from crimson.sim.world_state import WorldState

    _equip(monkeypatch, RelicId.TURRET_LOW)
    world = WorldState.build(world_size=1024.0, demo_mode_active=True, hardcore=False, quest_fail_retry_count=0)
    world.players.append(_pistol_player())
    idx = _build_turret(world.state, world.creatures, world.players[0])
    before_hp = float(world.creatures.entries[idx].hp)

    def _fake_projectile_step(*args: object, **kwargs: object) -> list:
        from typing import cast

        from crimson.projectiles.runtime import PrimaryStepCtx

        ctx = cast(PrimaryStepCtx, args[0])
        runtime = ctx.options.creature_damage_runtime
        assert runtime is not None
        runtime.apply_creature_damage(idx, 1000.0, int(CreatureDamageType.BULLET), Vec2(), OwnerRef.from_player(0))
        return []

    monkeypatch.setattr(world.state.projectiles, "step", _fake_projectile_step)
    world.step(
        0.016,
        inputs=None,
        world_size=1024.0,
        damage_scale_by_type={},
        detail_preset=5,
        fx_queue=FxQueue(),
        fx_queue_rotated=FxQueueRotated(),
        game_mode=GameMode.SURVIVAL,
        perk_progression_enabled=False,
    )

    assert float(world.creatures.entries[idx].hp) == before_hp
    assert world.creatures.entries[idx].active


def test_knockback_moves_a_turret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Integrated in tick_turret itself (not creatures/runtime.py's shared
    # per-creature loop) specifically so it isn't skipped while the Freeze
    # bonus is active - see test_knockback_still_moves_a_turret_during_freeze.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    start_pos = Vec2(entry.pos.x, entry.pos.y)
    entry.vel = Vec2(200.0, 0.0)

    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=pool.entries, dt=1.0 / 60.0)

    assert pool.entries[idx].pos.x > start_pos.x


def test_knockback_still_moves_a_turret_during_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: the freeze bonus short-circuits creatures/runtime.py's
    # entire shared per-creature loop, which used to be where the knockback
    # integration lived - moved into tick_turret (called independently from
    # sim/world_state.py) so it keeps working during Freeze.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    state.bonuses.freeze = 5.0
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    start_pos = Vec2(entry.pos.x, entry.pos.y)
    entry.vel = Vec2(200.0, 0.0)

    turret.tick_turret(entry, idx, player=player, state=state, players=[player], creatures=pool.entries, dt=1.0 / 60.0)

    assert pool.entries[idx].pos.x > start_pos.x


def test_turret_gets_its_own_man_bomb_explosion(monkeypatch: pytest.MonkeyPatch) -> None:
    # Man Bomb (and the other 3 periodic self-triggered perks - Hot Tempered,
    # Fire Cough, Living Fortress) only ever ran through apply_player_perk_ticks,
    # which tick_turret never called - so a turret never got them at all.
    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.turret_man_bomb_timer = 3.9
    player.perk_counts[int(PerkId.MAN_BOMB)] = 1

    victim_idx = pool.spawn_init(
        CreatureInit(
            origin_template_id=0, pos=Vec2(entry.pos.x + 50.0, entry.pos.y), heading=0.0, phase_seed=0,
            health=1000.0, max_health=1000.0,
        ),
    )
    before_hp = float(pool.entries[victim_idx].hp)

    from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime

    turret.tick_turret(
        entry, idx, player=player, state=state, players=[player], creatures=pool.entries, dt=0.2,
        creature_damage_runtime=DirectCreatureDamageRuntime(creatures=pool.entries),
    )

    assert float(pool.entries[victim_idx].hp) < before_hp
    # The turret's own cycle is independent of the real player's timer.
    assert player.man_bomb_timer == 0.0


def test_man_bombs_own_explosion_never_damages_a_turret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Man Bomb calls creature_apply_damage_with_lethal_followup
    # directly (perks/impl/man_bomb.py), bypassing sim/world_state.py's
    # apply_creature_damage wrapper entirely - the is_turret guard needs to
    # live in the lower-level shared function to catch this.
    from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime

    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.pos = Vec2(500.0, 500.0)
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.pos = Vec2(player.pos.x + 50.0, player.pos.y)  # well inside Man Bomb's 140px radius
    before_hp = float(entry.hp)

    player.man_bomb_timer = 3.9
    player.perk_counts[int(PerkId.MAN_BOMB)] = 1
    player_update(
        player,
        PlayerInput(aim=Vec2(player.pos.x + 1.0, player.pos.y)),
        0.2,
        state,
        players=[player],
        creatures=pool.entries,
        creature_damage_runtime=DirectCreatureDamageRuntime(creatures=pool.entries),
    )

    assert float(pool.entries[idx].hp) == before_hp


def test_turret_does_not_bite_the_player_or_trigger_contact_fx(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: only is_barrel was excluded from the creature-vs-player
    # contact-interaction pipeline (bite SFX, blood-spill FX, Energizer
    # eating, Plaguebearer infection) - a turret standing right next to the
    # player (it spawns TURRET_SPAWN_OFFSET away) would otherwise be treated
    # as if it were biting them.
    from tests.support.factories import make_creature_update_options

    _equip(monkeypatch, RelicId.TURRET_LOW)
    state = GameplayState()
    pool = CreaturePool()
    player = _pistol_player()
    player.pos = Vec2(500.0, 500.0)
    idx = _build_turret(state, pool, player)
    entry = pool.entries[idx]
    entry.pos = Vec2(player.pos.x + 10.0, player.pos.y)  # well within the 30-unit bite range

    options = make_creature_update_options(state=state, players=[player])
    pool.update(1.0 / 60.0, options=options)

    assert entry.attack_cooldown == 0.0
    assert player.health == 100.0
