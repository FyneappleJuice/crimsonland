from __future__ import annotations

from pathlib import Path

from crimson.game_modes import GameMode
from crimson.modes.base_gameplay_mode import BaseGameplayMode
from crimson.modes.maps_mode import MapsMode
from crimson.modes.quest_mode import QuestMode
from crimson.modes.rush_mode import RushMode
from crimson.modes.survival_mode import SurvivalMode
from crimson.modes.tutorial_mode import TutorialMode
from crimson.modes.typo_mode import TypoShooterMode
from grim.rand import Crand
from grim.view import ViewContext


def test_modes_construct_without_window(assets_dir: Path, make_mode_config) -> None:
    ctx = ViewContext(assets_dir=assets_dir)

    for game_mode, mode in (
        (GameMode.SURVIVAL, SurvivalMode(ctx, config=make_mode_config(game_mode=GameMode.SURVIVAL), audio_rng=Crand(0xBEEF))),
        (GameMode.RUSH, RushMode(ctx, config=make_mode_config(game_mode=GameMode.RUSH), audio_rng=Crand(0xBEEF))),
        (GameMode.QUESTS, QuestMode(ctx, config=make_mode_config(game_mode=GameMode.QUESTS), audio_rng=Crand(0xBEEF))),
        (
            GameMode.TUTORIAL,
            TutorialMode(ctx, config=make_mode_config(game_mode=GameMode.TUTORIAL), audio_rng=Crand(0xBEEF)),
        ),
        (GameMode.TYPO, TypoShooterMode(ctx, config=make_mode_config(game_mode=GameMode.TYPO), audio_rng=Crand(0xBEEF))),
        (GameMode.MAPS, MapsMode(ctx, config=make_mode_config(game_mode=GameMode.MAPS), audio_rng=Crand(0xBEEF))),
    ):
        assert isinstance(mode, BaseGameplayMode)
        assert mode._base_dir == make_mode_config(game_mode=game_mode).path.parent


def test_maps_mode_folds_fork_shot_into_the_bonus_pool(assets_dir: Path, make_mode_config) -> None:
    ctx = ViewContext(assets_dir=assets_dir)

    survival = SurvivalMode(ctx, config=make_mode_config(game_mode=GameMode.SURVIVAL), audio_rng=Crand(0xBEEF))
    maps = MapsMode(ctx, config=make_mode_config(game_mode=GameMode.MAPS), audio_rng=Crand(0xBEEF))

    # Fork: the Fork Shot / Blade bonuses are folded into the drop pool in every
    # mode (fork_bonus_in_pool default on).
    assert survival._sim_session is not None
    assert survival._sim_session.world.state.fork_bonus_in_pool is True
    assert maps._sim_session is not None
    assert maps._sim_session.world.state.fork_bonus_in_pool is True
