from __future__ import annotations

from grim.geom import Vec2
from grim.sfx_map import SfxId

from ...creatures.damage_types import CreatureDamageType
from ...math_parity import f32, x87_pc24_add, x87_pc24_hypot, x87_pc24_mul, x87_pc24_sub
from ..helpers import perk_active
from ..ids import PerkId
from ..impl.like_clockwork import like_clockwork_rate_mult
from ..runtime.hook_types import PerkHooks
from ..runtime.player_tick_context import PlayerPerkTickCtx

# Not native: Man Bomb reworked from an 8-way ion-projectile ring (4x Ion
# Minigun + 4x Ion Rifle bolts, fired at fixed 45-degree spacing) into a
# single instant nuke centered on the player - the ring read as a handful of
# stray bolts that mostly missed anything not standing right next to the
# player, rather than the "man bomb" the name promises. Numbers are a
# first-pass balance guess (roughly matching the old ring's total output
# against a single adjacent target), easy to retune by feel.
MAN_BOMB_NUKE_RADIUS = 140.0
MAN_BOMB_NUKE_DAMAGE_PER_PIXEL = 0.35


def tick_man_bomb(ctx: PlayerPerkTickCtx) -> None:
    if not perk_active(ctx.perk_player, PerkId.MAN_BOMB):
        ctx.player.man_bomb_timer = 0.0
        return

    ctx.player.man_bomb_timer = x87_pc24_add(
        float(ctx.player.man_bomb_timer),
        float(ctx.dt) * like_clockwork_rate_mult(ctx.perk_player),
    )
    if ctx.player.man_bomb_timer > ctx.state.perk_intervals.man_bomb:
        from ...creatures.damage import creature_apply_damage_with_lethal_followup

        origin = ctx.player_pos_before_move
        owner = ctx.owner_ref_for_player_projectiles(ctx.state, ctx.player.index).without_run_mod_affinity()
        efficacy = float(ctx.perk_player.stats.perk_efficacy)

        ctx.state.effects.spawn_explosion_burst(
            pos=origin,
            scale=1.2,
            rng=ctx.state.rng,
            detail_preset=5,
        )

        if ctx.creatures is not None and ctx.creature_damage_runtime is not None and ctx.players is not None:
            # Not native: suppress the normal death-triggered bonus drop roll
            # while resolving a multi-kill AoE hit, same as Final Revenge and
            # the native Nuke bonus - otherwise a big blast can spam several
            # bonus pickups from one proc.
            ctx.state.bonus_spawn_guard = True
            for creature_idx, creature in enumerate(ctx.creatures):
                if not creature.active:
                    continue
                dx = x87_pc24_sub(creature.pos.x, origin.x)
                dy = x87_pc24_sub(creature.pos.y, origin.y)
                if abs(dx) > MAN_BOMB_NUKE_RADIUS or abs(dy) > MAN_BOMB_NUKE_RADIUS:
                    continue
                remaining = x87_pc24_sub(MAN_BOMB_NUKE_RADIUS, x87_pc24_hypot(dx, dy))
                if remaining <= 0.0:
                    continue
                damage = x87_pc24_mul(x87_pc24_mul(remaining, MAN_BOMB_NUKE_DAMAGE_PER_PIXEL), efficacy)
                creature_apply_damage_with_lethal_followup(
                    creature,
                    creature_index=int(creature_idx),
                    damage_amount=damage,
                    damage_type=CreatureDamageType.EXPLOSION,
                    impulse=Vec2(),
                    owner=owner,
                    dt=float(ctx.dt),
                    players=ctx.players,
                    rng=ctx.state.rng,
                    effects=ctx.state.effects,
                    creature_damage_runtime=ctx.creature_damage_runtime,
                )
            ctx.state.bonus_spawn_guard = False

        # Not native: half volume (sfx_queue_quiet) - landed louder than
        # intended at the default level for something that can repeat every
        # few seconds.
        ctx.state.sfx_queue_quiet.append(SfxId.EXPLOSION_LARGE)
        ctx.state.sfx_queue_quiet.append(SfxId.SHOCKWAVE)

        ctx.player.man_bomb_timer = x87_pc24_sub(
            float(ctx.player.man_bomb_timer),
            float(ctx.state.perk_intervals.man_bomb),
        )
        ctx.state.perk_intervals.man_bomb = f32(4.0)


HOOKS = PerkHooks(
    perk_id=PerkId.MAN_BOMB,
    player_tick_steps=(tick_man_bomb,),
)
