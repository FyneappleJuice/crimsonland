from __future__ import annotations

"""Regression coverage for linking the two level-up panels' Cancel buttons
(survival_mode.py / quest_mode.py's _update_perk_ui).

Cancel on either panel now backs out of the whole level-up instead of only
resolving its own list, leaving the other panel stranded open. Neither side
marks its choice list dirty on a cancel, so reopening later still offers the
exact same choices - that part was already true before this change (only a
real pick marks a list dirty); these tests pin it down explicitly since it's
now something players can rely on across a cancel-and-reopen round trip.

`_update_perk_ui` needs live UI resources this test environment can't load,
and `handle_input` itself needs a real mouse/window to detect a click, so
`PerkMenuController.handle_input`/`RunModMenuController.handle_input` are
stubbed to reproduce exactly what a real Cancel click does to their own
state (flip `cancel_activated`, close, return None) - only the *linking*
logic in `_update_perk_ui` is under test, not the click detection itself.
"""

from pathlib import Path

from crimson.game_modes import GameMode
from crimson.modes.components.perk_menu_controller import PerkMenuController
from crimson.modes.components.perk_prompt_controller import PerkPromptState
from crimson.modes.components.run_mod_menu_controller import RunModMenuController
from crimson.modes.survival_mode import SurvivalMode
from crimson.perks.ids import PerkId
from crimson.perks.selection import perk_selection_prepared_choices
from grim.rand import Crand
from grim.view import ViewContext


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "assets"


def _quiet_perk_prompt(monkeypatch) -> None:
    monkeypatch.setattr(PerkPromptState, "poll_open_request", lambda self, **kw: False)
    monkeypatch.setattr(PerkPromptState, "begin_frame", lambda self: None)
    monkeypatch.setattr(PerkPromptState, "tick_timer", lambda self, **kw: None)
    monkeypatch.setattr(PerkPromptState, "tick_pulse", lambda self, dt: None)


def _fake_cancel(self, ctx, choices, *, dt_ui_ms):
    self._cancel_button.activated = True
    self.close()
    return None


def _fake_idle(self, ctx, choices, *, dt_ui_ms):
    """Mimics a frame with no interaction at all - panel stays open."""
    self._cancel_button.activated = False
    return None


def _fake_pick(self, ctx, choices, *, dt_ui_ms):
    """Mimics a real pick - closes the panel and returns a chosen index."""
    self.close()
    return 0


def _make_survival_mode(make_mode_config) -> SurvivalMode:
    config = make_mode_config(game_mode=GameMode.SURVIVAL)
    return SurvivalMode(ViewContext(assets_dir=_assets_dir()), config=config, audio_rng=Crand(0xBEEF))


def test_cancel_on_main_perk_panel_also_closes_the_run_mod_panel(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)
        _quiet_perk_prompt(monkeypatch)
        monkeypatch.setattr(PerkMenuController, "handle_input", _fake_cancel)
        monkeypatch.setattr(RunModMenuController, "handle_input", _fake_idle)

        mode._perk_menu.open_menu()
        mode._run_mod_menu.open_menu()

        mode._update_perk_ui(dt_ui_ms=16.0)

        assert mode._perk_menu.open is False
        assert mode._run_mod_menu.open is False
        assert mode._perk_round_had_pick is False  # a cancel, not a pick
    finally:
        mode.close()


def test_cancel_on_run_mod_panel_also_closes_the_main_perk_panel(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)
        _quiet_perk_prompt(monkeypatch)
        monkeypatch.setattr(PerkMenuController, "handle_input", _fake_idle)
        monkeypatch.setattr(RunModMenuController, "handle_input", _fake_cancel)

        mode._perk_menu.open_menu()
        mode._run_mod_menu.open_menu()

        mode._update_perk_ui(dt_ui_ms=16.0)

        assert mode._run_mod_menu.open is False
        assert mode._perk_menu.open is False
        assert mode._perk_round_had_pick is False
    finally:
        mode.close()


def test_picking_the_run_mod_choice_disables_the_perk_panels_cancel(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)
        _quiet_perk_prompt(monkeypatch)
        monkeypatch.setattr(PerkMenuController, "handle_input", _fake_idle)
        monkeypatch.setattr(RunModMenuController, "handle_input", _fake_pick)

        mode._perk_menu.open_menu()
        mode._run_mod_menu.open_menu()
        assert mode._perk_menu._cancel_button.enabled is True

        mode._update_perk_ui(dt_ui_ms=16.0)

        # The run-mod side picked and closed; the still-open perk panel's
        # Cancel must now be disabled - it has to be picked too, not
        # cancelled out from under the already-spent run-mod choice.
        assert mode._perk_menu.open is True
        assert mode._perk_menu._cancel_button.enabled is False

        # Confirm a disabled Cancel really is inert: even a "click" on it
        # produces no activation once enabled=False (button_update's own
        # contract), so a subsequent real cancel attempt cannot close it.
        def _fake_cancel_respecting_enabled(self, ctx, choices, *, dt_ui_ms):
            if not self._cancel_button.enabled:
                return None
            return _fake_cancel(self, ctx, choices, dt_ui_ms=dt_ui_ms)

        monkeypatch.setattr(PerkMenuController, "handle_input", _fake_cancel_respecting_enabled)
        mode._update_perk_ui(dt_ui_ms=16.0)
        assert mode._perk_menu.open is True
    finally:
        mode.close()


def test_picking_the_main_perk_disables_the_run_mod_panels_cancel(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        monkeypatch.setattr(mode, "_perk_menu_ui_context", lambda: None)
        _quiet_perk_prompt(monkeypatch)
        monkeypatch.setattr(PerkMenuController, "handle_input", _fake_pick)
        monkeypatch.setattr(RunModMenuController, "handle_input", _fake_idle)

        mode._perk_menu.open_menu()
        mode._run_mod_menu.open_menu()

        mode._update_perk_ui(dt_ui_ms=16.0)

        assert mode._run_mod_menu.open is True
        assert mode._run_mod_menu._cancel_button.enabled is False
    finally:
        mode.close()


def test_reopening_for_a_new_round_reenables_both_cancel_buttons(make_mode_config, monkeypatch) -> None:
    mode = _make_survival_mode(make_mode_config)
    try:
        mode._perk_menu.disable_cancel()
        mode._run_mod_menu.disable_cancel()

        mode._perk_menu.open_menu()
        mode._run_mod_menu.open_menu()

        assert mode._perk_menu._cancel_button.enabled is True
        assert mode._run_mod_menu._cancel_button.enabled is True
    finally:
        mode.close()


def test_choices_are_unchanged_after_a_cancel_and_reopen(make_mode_config) -> None:
    # Not a behavior this change introduced - only a real pick ever marks a
    # choice list dirty (perk_selection_pick / run_mod_selection_pick) - but
    # pinned explicitly since players can now rely on it across any cancel.
    mode = _make_survival_mode(make_mode_config)
    try:
        perk_state = mode.state.perk_selection
        perk_state.choices = [PerkId.FASTSHOT, PerkId.BARREL_GREASER]
        perk_state.choices_dirty = False

        before = perk_selection_prepared_choices(mode.sim_world.players, perk_state)
        mode._perk_menu.open_menu()
        mode._perk_menu.close()  # simulates a Cancel: no pick, so never marked dirty
        after = perk_selection_prepared_choices(mode.sim_world.players, perk_state)

        assert after == before
    finally:
        mode.close()
