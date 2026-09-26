from __future__ import annotations

"""Regression coverage for the perk-menu "chain into the next pending pick"
behavior (survival_mode.py / quest_mode.py's _update_perk_ui).

The mechanism has two parts that both need locking down:
1. A real pick (not Cancel/Escape) should auto-reopen the menu once both
   panels finish closing, instead of leaving the player to right-click again.
2. That reopen must wait one extra tick past "both panels closed" - the
   recorded PerkPickCommand/RunModPickCommand only gets applied by the
   deterministic session while sim_dt > 0, and sim_dt is forced to 0 for as
   long as the menu is considered active. Reopening on the very same tick
   the menu reports closed would flip it active again before the caller ever
   computes a nonzero sim_dt for that tick, so the queued pick would never
   actually apply - the exact bug this test suite catches.

`_update_perk_ui` touches live UI resources it isn't practical to load in a
test environment (draws/prompt widgets need real GPU-backed textures), so
those parts are stubbed out here; only the reopen-sequencing contract itself
is under test.
"""

from pathlib import Path

from crimson.game_modes import GameMode
from crimson.modes.components.perk_prompt_controller import PerkPromptState
from crimson.modes.survival_mode import SurvivalMode
from grim.rand import Crand
from grim.view import ViewContext


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "assets"


def _quiet_perk_prompt(monkeypatch) -> None:
    """Stub the passive-prompt widget's own GL-touching methods - unrelated
    to the reopen logic under test, and would otherwise need real resources."""

    monkeypatch.setattr(PerkPromptState, "poll_open_request", lambda self, **kw: False)
    monkeypatch.setattr(PerkPromptState, "begin_frame", lambda self: None)
    monkeypatch.setattr(PerkPromptState, "tick_timer", lambda self, **kw: None)
    monkeypatch.setattr(PerkPromptState, "tick_pulse", lambda self, dt: None)


def _make_survival_mode(make_mode_config) -> SurvivalMode:
    config = make_mode_config(game_mode=GameMode.SURVIVAL)
    return SurvivalMode(ViewContext(assets_dir=_assets_dir()), config=config, audio_rng=Crand(0xBEEF))


def test_reopen_waits_one_tick_past_the_pick_before_firing(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        _quiet_perk_prompt(monkeypatch)
        opened = []
        monkeypatch.setattr(mode, "_try_open_perk_menu", lambda: opened.append(True))
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)

        mode.state.perk_selection.pending_count = 1
        mode._perk_round_had_pick = True  # both panels just resolved with a real pick

        # Same tick the pick resolved: must NOT reopen yet - the caller still
        # needs one tick with the menu genuinely closed to let the queued
        # pick command actually apply.
        mode._update_perk_ui(dt_ui_ms=16.0)
        assert opened == []
        assert mode._perk_menu_reopen_pending is True
        assert mode._perk_round_had_pick is False

        # Next tick: the deferred flag fires now that a real tick has passed.
        mode._update_perk_ui(dt_ui_ms=16.0)
        assert opened == [True]
        assert mode._perk_menu_reopen_pending is False
    finally:
        mode.close()


def test_no_reopen_when_nothing_is_pending(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        _quiet_perk_prompt(monkeypatch)
        opened = []
        monkeypatch.setattr(mode, "_try_open_perk_menu", lambda: opened.append(True))
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)

        mode.state.perk_selection.pending_count = 0
        mode._perk_round_had_pick = True

        mode._update_perk_ui(dt_ui_ms=16.0)
        mode._update_perk_ui(dt_ui_ms=16.0)

        assert opened == []
    finally:
        mode.close()


def test_cancel_never_sets_the_reopen_intent(make_mode_config, monkeypatch) -> None:
    # A Cancel/Escape close never sets _perk_round_had_pick (only a real
    # pick does, in _update_perk_ui's own handle_input branches) - simulate
    # that "nothing was picked" state directly and confirm no auto-reopen
    # happens even though a pick is still pending (matches today's existing
    # "come back later" behavior for backing out of a level-up).
    mode = _make_survival_mode(make_mode_config)
    try:
        _quiet_perk_prompt(monkeypatch)
        opened = []
        monkeypatch.setattr(mode, "_try_open_perk_menu", lambda: opened.append(True))
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)

        mode.state.perk_selection.pending_count = 1
        mode._perk_round_had_pick = False
        mode._perk_menu_reopen_pending = False

        mode._update_perk_ui(dt_ui_ms=16.0)
        mode._update_perk_ui(dt_ui_ms=16.0)

        assert opened == []
        assert mode._perk_menu_reopen_pending is False
    finally:
        mode.close()
