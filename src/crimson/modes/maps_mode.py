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

from ..creatures.dummy import spawn_stationary_test_monster, spawn_test_dummy
from ..creatures.spawn import SURVIVAL_UPDATE_MAIN_SPAWN_POS_CALLERS, rand_survival_spawn_pos
from ..creatures.spawn_ids import SpawnId
from ..game_modes import GameMode
from ..replay import Replay, ReplayRecorder
from ..sim.sessions import DeterministicSession, MidStepContext, SurvivalSessionRuntime, survival_mid_step
from ..ui.sandbox_debug_panel import SandboxDebugPanel
from .survival_mode import SurvivalMode

__all__ = ["MAP_MODIFIERS", "MapModifier", "MapsMode", "MapsSessionRuntime", "SandboxSessionRuntime"]

# Not native: pushed below the HUD's weapon-icon block and XP panel (which
# together run up to ~Y170 at the largest HUD scale setting) so this text no
# longer overlaps them.
_MAPS_BANNER_POS = Vec2(18.0, 180.0)
_MAPS_BANNER_COLOR = rl.Color(220, 190, 140, 220)
_SANDBOX_HINT_POS = Vec2(18.0, 196.0)
_SANDBOX_HINT_COLOR = rl.Color(150, 210, 255, 220)
# Not native: sandbox placement/drag - how close (world px) a click needs to
# land to an existing test entity to grab it instead of doing nothing.
_SANDBOX_DRAG_HIT_RADIUS = 34.0
_SANDBOX_CURSOR_COLOR = rl.Color(255, 255, 255, 235)
_SANDBOX_CURSOR_OUTLINE = rl.Color(20, 20, 20, 200)
_SANDBOX_CURSOR_RADIUS = 5.0

# Not native: sandbox time scale - how fast in-game time moves relative to
# real time. Applied by scaling the per-frame dt handed to SurvivalMode's
# update() before anything else sees it, so it uniformly slows/speeds up
# movement, cooldowns, projectiles, animations - everything - the same way
# replay_playback_mode.py's own speed control already scales its dt.
_TIME_SCALE_STEPS: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
_DEFAULT_TIME_SCALE_INDEX = _TIME_SCALE_STEPS.index(1.0)
_TIME_SCALE_HINT_POS = Vec2(18.0, 212.0)
_TIME_SCALE_HINT_COLOR = rl.Color(230, 210, 140, 220)


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


class SandboxSessionRuntime(SurvivalSessionRuntime):
    """Not native: Maps' sandbox/testing-ground mode - a no-op `mid_step`
    means the entire survival spawn cascade (waves, milestones, dens, boss
    waves) never runs, so nothing appears in the arena except what the owner
    places by hand (creatures/dummy.py). Leveling/XP/the normal perk-menu
    stay untouched - only ambient monster spawning is suppressed."""

    def needs_mid_step(self) -> bool:
        return False


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
        # Not native: sandbox placement/drag state (see _handle_input's F6/F7/F8
        # handling below).
        self._sandbox_edit_mode = False
        self._sandbox_drag_index: int | None = None
        self._sandbox_drag_offset = Vec2()
        self._sandbox_panel = SandboxDebugPanel()
        self._sandbox_time_scale_index = _DEFAULT_TIME_SCALE_INDEX
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
        # Not native: Maps is now a sandbox/testing-ground mode - see
        # SandboxSessionRuntime's docstring. The rolled MapModifier still
        # exists for the map-select screen's flavor text, but no longer
        # drives any spawn behavior (there's no ambient spawning to scale).
        session.mode_runtime = SandboxSessionRuntime(spawn=base_runtime.spawn)
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

    # --- sandbox placement / drag (not native) -----------------------------

    def _handle_input(self) -> None:
        super()._handle_input()
        if self._game_over_active:
            return

        # Not native: time scale - works regardless of edit mode/panel state,
        # since you'd want to slow down or fast-forward while just watching
        # combat happen too, not only while placing test entities.
        if rl.is_key_pressed(rl.KeyboardKey.KEY_MINUS):
            self._sandbox_change_time_scale(-1)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_EQUAL):
            self._sandbox_change_time_scale(1)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_ZERO):
            self._sandbox_time_scale_index = _DEFAULT_TIME_SCALE_INDEX

        # Not native: F4 (panel)/F6 (edit mode) are independent toggles, not a
        # mutually-exclusive pair - both can be on at once, so you can leave
        # the Monster Mods panel open (to see/tweak the current tier+affix
        # pick) while also placing test entities with F7/F8, instead of
        # having to close the panel first every time.
        if rl.is_key_pressed(rl.KeyboardKey.KEY_F4):
            self._sandbox_panel.toggle()
            self._paused = self._sandbox_panel.open or self._sandbox_edit_mode

        if rl.is_key_pressed(rl.KeyboardKey.KEY_F6):
            self._sandbox_edit_mode = not self._sandbox_edit_mode
            # Edit mode pauses the sim outright (same flag TAB already toggles)
            # so a click-drag can never double as a trigger-pull or movement
            # input underneath it.
            self._paused = self._sandbox_panel.open or self._sandbox_edit_mode
            self._sandbox_drag_index = None

        if self._sandbox_edit_mode:
            if rl.is_key_pressed(rl.KeyboardKey.KEY_F7):
                tier, affixes = self._sandbox_panel.monster_mod_selection()
                spawn_test_dummy(self.creatures, self._sandbox_mouse_world(), tier=tier, forced_affixes=affixes)
            if rl.is_key_pressed(rl.KeyboardKey.KEY_F8):
                tier, affixes = self._sandbox_panel.monster_mod_selection()
                spawn_stationary_test_monster(
                    self.creatures, self._sandbox_mouse_world(), tier=tier, forced_affixes=affixes,
                )

        if self._sandbox_panel.open:
            self._sandbox_panel.handle_input(
                players=self.sim_world.players, state=self.state, creatures=self.creatures.entries,
            )
            return  # panel owns the mouse while it's open (world click-drag/delete stays blocked)

        if not self._sandbox_edit_mode:
            return

        self._sandbox_update_drag()

    def _sandbox_time_scale(self) -> float:
        return _TIME_SCALE_STEPS[int(self._sandbox_time_scale_index)]

    def _sandbox_change_time_scale(self, delta: int) -> None:
        idx = int(self._sandbox_time_scale_index) + int(delta)
        self._sandbox_time_scale_index = max(0, min(idx, len(_TIME_SCALE_STEPS) - 1))

    def update(self, dt: float) -> None:
        # Not native: scale the whole frame's dt before SurvivalMode ever sees
        # it, so slow-mo/fast-forward affects movement, cooldowns, projectiles,
        # and animations uniformly - same lever replay_playback_mode.py's own
        # speed control already pulls (scaling dt before the tick advances).
        super().update(float(dt) * self._sandbox_time_scale())
        self._sandbox_revive_dead_players()

    def _death_transition_ready(self) -> bool:
        # Not native: sandbox is a testing ground, not a real run - dying here
        # shouldn't trigger SurvivalMode's normal game-over flow (high-score
        # record, replay save, game-over UI), which assumes a real run's
        # context. _sandbox_revive_dead_players heals the player back up
        # before this would ever matter anyway; this is the hard guarantee in
        # case a single large frame dt (e.g. under a fast time-scale setting)
        # ever pushed death_timer negative before that heal-check runs.
        return False

    def _sandbox_revive_dead_players(self) -> None:
        """Heals any player back to full HP the instant they'd otherwise die,
        so sandbox testing never ends a session (and can't hit whatever the
        normal death/game-over path assumes about a real run's state)."""
        for player in self.sim_world.players:
            if float(player.health) <= 0.0:
                player.health = 100.0
                player.death_timer = 16.0

    def _sandbox_mouse_world(self) -> Vec2:
        return self.screen_to_world(Vec2.from_xy(rl.get_mouse_position()))

    def _sandbox_nearest_entity(self, mouse_world: Vec2, *, max_dist: float) -> int | None:
        best: int | None = None
        best_dist = float(max_dist)
        for idx, creature in enumerate(self.creatures.entries):
            if not creature.active:
                continue
            dist = creature.pos.distance_to(mouse_world)
            if dist <= best_dist:
                best_dist = dist
                best = idx
        return best

    def _sandbox_update_drag(self) -> None:
        mouse_world = self._sandbox_mouse_world()

        if self._sandbox_drag_index is not None:
            if rl.is_mouse_button_down(rl.MouseButton.MOUSE_BUTTON_LEFT):
                idx = self._sandbox_drag_index
                if 0 <= idx < len(self.creatures.entries):
                    self.creatures.entries[idx].pos = mouse_world + self._sandbox_drag_offset
                return
            self._sandbox_drag_index = None

        # Not native: RMB deletes the nearest test entity outright - a
        # deliberate removal, so (unlike a combat death) it never queues a
        # respawn; that's still on a 5s timer, but only for a monster that
        # actually died to a hit (see queue_stationary_monster_respawn).
        if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_RIGHT):
            idx = self._sandbox_nearest_entity(mouse_world, max_dist=_SANDBOX_DRAG_HIT_RADIUS)
            if idx is not None:
                self.creatures.entries[idx].active = False
                if self._sandbox_drag_index == idx:
                    self._sandbox_drag_index = None
            return

        if not rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
            return

        idx = self._sandbox_nearest_entity(mouse_world, max_dist=_SANDBOX_DRAG_HIT_RADIUS)
        if idx is None:
            return
        creature = self.creatures.entries[idx]
        self._sandbox_drag_offset = creature.pos - mouse_world
        self._sandbox_drag_index = idx

    def draw(self) -> None:
        super().draw()
        if self._game_over_active:
            return
        # Not native: no ambient spawning happens anymore (SandboxSessionRuntime),
        # so the old "boss inbound" banner would just be a lie - swapped for a
        # plain sandbox-mode label instead of the rolled MapModifier's name.
        self._draw_ui_text(
            "Sandbox - no ambient spawns, place test targets by hand",
            _MAPS_BANNER_POS,
            _MAPS_BANNER_COLOR,
            scale=0.9,
        )
        hint = (
            "Edit mode ON (paused) - F7 dummy, F8 monster, LMB drag, RMB delete, F6 to exit"
            if self._sandbox_edit_mode
            else "F6: sandbox edit mode (place/drag/delete test dummies)  F4: perk/relic/run-mod/weapon/monster-mods panel"
        )
        self._draw_ui_text(hint, _SANDBOX_HINT_POS, _SANDBOX_HINT_COLOR, scale=0.75)
        self._draw_ui_text(
            f"Time scale: {self._sandbox_time_scale():.2f}x  (- / = to adjust, 0 to reset)",
            _TIME_SCALE_HINT_POS,
            _TIME_SCALE_HINT_COLOR,
            scale=0.75,
        )
        self._sandbox_panel.draw(self)
        self._draw_sandbox_cursor()

    def _draw_sandbox_cursor(self) -> None:
        # Not native: the game hides the OS cursor everywhere (loop_view.py's
        # rl.hide_cursor()) and normally relies on the aim reticle to show
        # where the mouse is - but the reticle is driven by the sim tick,
        # which we deliberately stop (self._paused) while editing/the panel
        # is open, so it freezes in place instead of following the mouse.
        # Draw a plain screen-space crosshair here instead, read straight off
        # the OS mouse position so it keeps tracking regardless of pause.
        if not (self._sandbox_edit_mode or self._sandbox_panel.open):
            return
        mouse = rl.get_mouse_position()
        r = _SANDBOX_CURSOR_RADIUS
        rl.draw_circle_lines(int(mouse.x), int(mouse.y), r + 1.0, _SANDBOX_CURSOR_OUTLINE)
        rl.draw_circle_lines(int(mouse.x), int(mouse.y), r, _SANDBOX_CURSOR_COLOR)
        rl.draw_line(int(mouse.x - r * 2), int(mouse.y), int(mouse.x - r), int(mouse.y), _SANDBOX_CURSOR_COLOR)
        rl.draw_line(int(mouse.x + r), int(mouse.y), int(mouse.x + r * 2), int(mouse.y), _SANDBOX_CURSOR_COLOR)
        rl.draw_line(int(mouse.x), int(mouse.y - r * 2), int(mouse.x), int(mouse.y - r), _SANDBOX_CURSOR_COLOR)
        rl.draw_line(int(mouse.x), int(mouse.y + r), int(mouse.x), int(mouse.y + r * 2), _SANDBOX_CURSOR_COLOR)
