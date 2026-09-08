from __future__ import annotations

import math

import msgspec
from grim.audio import AudioState
from grim.config import CrimsonConfig
from grim.console import ConsoleState
from grim.geom import Vec2
from grim.rand import Crand
from grim.raylib_api import rl
from grim.view import ViewContext

from ..creatures.spawn import SURVIVAL_UPDATE_MAIN_SPAWN_POS_CALLERS, rand_survival_spawn_pos
from ..creatures.spawn_ids import SpawnId
from ..game_modes import GameMode
from ..replay import Replay, ReplayRecorder
from ..sim.sessions import DeterministicSession, MidStepContext, SurvivalSessionRuntime, survival_mid_step
from .survival_mode import SurvivalMode

__all__ = ["MAP_MODIFIERS", "MapModifier", "MapsMode", "MapsSessionRuntime"]

_MAPS_BANNER_POS = Vec2(18.0, 4.0)
_MAPS_BANNER_COLOR = rl.Color(220, 190, 140, 220)


class MapModifier(msgspec.Struct, frozen=True):
    """A rolled-map affix bundle: no native equivalent, this is an original addition.

    `spawn_time_scale` reshapes the survival wave-spawn formula's pacing (same
    formula, faster or slower clock) rather than inventing a new one. The boss
    is a guaranteed, one-time spawn at `boss_trigger_ms` of *real* elapsed time
    (not scaled), so every map has a predictable boss arrival regardless of how
    aggressive its ambient spawn pacing is.
    """

    key: str
    name: str
    tagline: str
    spawn_time_scale: float
    boss_spawn_id: SpawnId
    boss_name: str
    boss_trigger_ms: float = 60_000.0


MAP_MODIFIERS: tuple[MapModifier, ...] = (
    MapModifier(
        key="zombie_fields",
        name="Zombie Fields",
        tagline="A steady grind. Nothing fancy, just a lot of them.",
        spawn_time_scale=1.15,
        boss_spawn_id=SpawnId.ZOMBIE_BOSS_SPAWNER_00,
        boss_name="Zombie Spawner",
    ),
    MapModifier(
        key="lizard_swamp",
        name="Lizard Swamp",
        tagline="Faster spawns. Keep moving.",
        spawn_time_scale=1.35,
        boss_spawn_id=SpawnId.LIZARD_CONST_YELLOW_BOSS_30,
        boss_name="Lizard Boss",
    ),
    MapModifier(
        key="alien_outpost",
        name="Alien Outpost",
        tagline="A rough pace from the very first minute.",
        spawn_time_scale=1.55,
        boss_spawn_id=SpawnId.ALIEN_CONST_RED_BOSS_2C,
        boss_name="Alien Boss",
    ),
    MapModifier(
        key="spider_nest",
        name="Spider Nest",
        tagline="Heavy swarms. Bring a wide weapon.",
        spawn_time_scale=1.45,
        boss_spawn_id=SpawnId.SPIDER_BOSS_3A,
        boss_name="Spider Boss",
    ),
    MapModifier(
        key="crimson_hive",
        name="Crimson Hive",
        tagline="The hardest roll. Good luck.",
        spawn_time_scale=1.8,
        boss_spawn_id=SpawnId.SPIDER_SP1_CONST_RED_BOSS_3B,
        boss_name="Hive Guardian",
    ),
)


class MapsSessionRuntime(SurvivalSessionRuntime):
    modifier: MapModifier = msgspec.field(default_factory=lambda: MAP_MODIFIERS[0])
    boss_spawned: bool = False

    def mid_step(self, ctx: MidStepContext) -> None:
        scaled_ctx = msgspec.structs.replace(
            ctx,
            elapsed_before_ms=float(ctx.elapsed_before_ms) * float(self.modifier.spawn_time_scale),
        )
        survival_mid_step(scaled_ctx, self.spawn)

        if self.boss_spawned or float(ctx.elapsed_before_ms) < float(self.modifier.boss_trigger_ms):
            return
        self.boss_spawned = True
        state = ctx.world.state
        world_size = float(ctx.world_size)
        pos = rand_survival_spawn_pos(
            state.rng,
            terrain_width=int(world_size),
            terrain_height=int(world_size),
            callers=SURVIVAL_UPDATE_MAIN_SPAWN_POS_CALLERS,
        )
        center = world_size / 2.0
        heading = math.atan2(center - pos.y, center - pos.x)
        ctx.world.creatures.spawn_template(self.modifier.boss_spawn_id, pos, heading, state.rng)


class MapsMode(SurvivalMode):
    """Survival with a rolled map affix and a guaranteed boss.

    An original mode, not present in the 2004 original or this rewrite's
    upstream: reuses Survival's entire runtime (HUD, perks, replay recording,
    game-over flow) and only swaps in a `MapsSessionRuntime` that reshapes
    spawn pacing and injects a boss. See `screens/panels/maps_menu.py` for the
    map-select screen that rolls `current_modifier` before a run starts.
    """

    def __init__(
        self,
        ctx: ViewContext,
        *,
        config: CrimsonConfig,
        console: ConsoleState | None = None,
        audio: AudioState | None = None,
        audio_rng: Crand,
    ) -> None:
        # `SurvivalMode.__init__` calls `self._new_sim_session()` (our override)
        # before returning, so these must be set before `super().__init__()` runs.
        self.current_modifier: MapModifier = MAP_MODIFIERS[0]
        self._modifier_rolled = False
        super().__init__(
            ctx,
            config=config,
            console=console,
            audio=audio,
            audio_rng=audio_rng,
        )
        self.default_game_mode_id = GameMode.MAPS

    def roll_modifier(self) -> MapModifier:
        index = self.state.rng.rand() % len(MAP_MODIFIERS)
        self.current_modifier = MAP_MODIFIERS[index]
        self._modifier_rolled = True
        return self.current_modifier

    def _new_sim_session(self) -> DeterministicSession:
        session = super()._new_sim_session()
        base_runtime = session.mode_runtime
        assert isinstance(base_runtime, SurvivalSessionRuntime)
        session.mode_runtime = MapsSessionRuntime(spawn=base_runtime.spawn, modifier=self.current_modifier)
        # Maps is the one mode that folds the non-native Fork Shot bonus into the
        # random drop pool (see bonuses/selection.py). Every native mode leaves
        # the original drop table untouched.
        session.world.state.fork_bonus_in_pool = True
        return session

    def open(self) -> None:
        if not self._modifier_rolled:
            self.roll_modifier()
        super().open()
        if self._replay_recorder is not None:
            new_header = msgspec.structs.replace(self._replay_recorder.header, game_mode_id=GameMode.MAPS)
            self._replay_recorder = ReplayRecorder(new_header)
        self._modifier_rolled = False

    def _replay_output_basename(self, *, stamp: str, replay: Replay) -> str:
        _ = replay
        score = int(self.player.experience)
        return f"maps_{self.current_modifier.key}_{stamp}_score{score}"

    def draw(self) -> None:
        super().draw()
        if self._game_over_active:
            return
        modifier = self.current_modifier
        self._draw_ui_text(
            f"{modifier.name} - {modifier.boss_name} inbound",
            _MAPS_BANNER_POS,
            _MAPS_BANNER_COLOR,
            scale=0.9,
        )
