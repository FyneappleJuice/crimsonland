from __future__ import annotations

"""Not native: controller for the secondary "run mod" choice panel, drawn
beside the perk-selection panel at every level-up. Mirrors PerkMenuController's
shape but is deliberately independent (not a genericized PerkMenuController)
since the perk controller carries perk-specific sponsor-text branching this
pool has no equivalent for."""

from collections.abc import Sequence

from grim.assets import TextureId
from grim.math import clamp
from grim.raylib_api import rl
from grim.sfx_map import SfxId

from ...run_mods.display import run_mod_choice_display_description, run_mod_choice_display_name
from ...run_mods.state import RunModChoice
from ...ui.layout import ui_origin, ui_scale
from ...ui.menu_panel import draw_classic_menu_panel, draw_menu_panel_hardware
from ...ui.perk_menu import (
    UiButtonState,
    button_draw,
    button_update,
    button_width,
    draw_menu_item,
    draw_ui_text,
    menu_item_hit_rect,
    wrap_ui_text,
)
from ...ui.run_mod_menu import (
    RUN_MOD_MENU_TRANSITION_MS,
    RunModMenuLayout,
    run_mod_menu_compute_layout,
    run_mod_menu_panel_slide_x,
)
from .perk_menu_controller import PerkMenuRuntime, PerkMenuUiContext

UI_TEXT_COLOR = rl.Color(220, 220, 220, 255)
_TITLE_COLOR = rl.Color(240, 200, 80, 255)
_TITLE_TEXT = "Modifier"


class RunModMenuController:
    def __init__(
        self,
        *,
        cancel_label: str = "Cancel",
        runtime: PerkMenuRuntime | None = None,
    ) -> None:
        self._cancel_label = cancel_label
        self._runtime = runtime if runtime is not None else PerkMenuRuntime()
        self.reset()

    @property
    def open(self) -> bool:
        return bool(self._open)

    @open.setter
    def open(self, value: bool) -> None:
        if not value and self._open:
            self.close()
        else:
            self._open = bool(value)

    @property
    def active(self) -> bool:
        return bool(self._open) or self._timeline_ms > 1e-3

    @property
    def timeline_ms(self) -> float:
        return float(self._timeline_ms)

    def reset(self) -> None:
        self._layout = RunModMenuLayout()
        self._cancel_button = UiButtonState(self._cancel_label)
        self._open = False
        self._selected_index = 0
        self._timeline_ms = 0.0

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._runtime.on_close()

    def open_menu(self) -> None:
        if self._open:
            return
        self._open = True
        self._selected_index = 0

    def tick_timeline(self, dt_ui_ms: float, *, hold: bool = False) -> None:
        """`hold=True` freezes the timeline (used to delay sliding in until
        the perk panel has fully arrived - see the mode's `_update_perk_ui`)."""
        if hold:
            return
        if self._open:
            self._timeline_ms = clamp(self._timeline_ms + float(dt_ui_ms), 0.0, RUN_MOD_MENU_TRANSITION_MS)
        else:
            self._timeline_ms = clamp(self._timeline_ms - float(dt_ui_ms), 0.0, RUN_MOD_MENU_TRANSITION_MS)

    def handle_input(
        self,
        ctx: PerkMenuUiContext,
        choices: Sequence[RunModChoice],
        *,
        dt_ui_ms: float,
    ) -> int | None:
        if not choices:
            self.close()
            return None

        if self._selected_index >= len(choices):
            self._selected_index = 0

        if rl.is_key_pressed(rl.KeyboardKey.KEY_DOWN):
            self._selected_index = (self._selected_index + 1) % len(choices)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_UP):
            self._selected_index = (self._selected_index - 1) % len(choices)

        screen_w = float(rl.get_screen_width())
        screen_h = float(rl.get_screen_height())
        scale = ui_scale(screen_w, screen_h)
        origin = ui_origin(screen_w, screen_h, scale)
        slide_x = run_mod_menu_panel_slide_x(self._timeline_ms, layout=self._layout)

        click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

        computed = run_mod_menu_compute_layout(
            self._layout,
            screen_w=screen_w,
            origin=origin,
            scale=scale,
            choice_count=len(choices),
            panel_slide_x=slide_x,
        )

        for idx, choice in enumerate(choices):
            label = run_mod_choice_display_name(choice, violence_disabled=int(ctx.violence_disabled))
            item_pos = computed.list_pos.offset(dy=float(idx) * computed.list_step_y)
            rect = menu_item_hit_rect(ctx.resources, label, pos=item_pos, scale=scale)
            if rect.contains(ctx.mouse):
                self._selected_index = idx
                if click:
                    self._runtime.play_sfx(SfxId.UI_BUTTONCLICK)
                    self.close()
                    return int(idx)
                break

        cancel_w = button_width(
            ctx.resources,
            self._cancel_button.label,
            scale=scale,
            force_wide=self._cancel_button.force_wide,
        )
        if button_update(
            self._cancel_button,
            pos=computed.cancel_pos,
            width=cancel_w,
            dt_ms=float(dt_ui_ms),
            mouse=ctx.mouse,
            click=click,
        ):
            self._runtime.play_sfx(SfxId.UI_BUTTONCLICK)
            self.close()
            return None

        if rl.is_key_pressed(rl.KeyboardKey.KEY_ENTER) or rl.is_key_pressed(rl.KeyboardKey.KEY_SPACE):
            self._runtime.play_sfx(SfxId.UI_BUTTONCLICK)
            self.close()
            return int(self._selected_index)
        return None

    def draw(self, ctx: PerkMenuUiContext, choices: Sequence[RunModChoice]) -> None:
        menu_t = clamp(self._timeline_ms / RUN_MOD_MENU_TRANSITION_MS, 0.0, 1.0)
        if menu_t <= 1e-3:
            return

        if not choices:
            return
        if self._selected_index >= len(choices):
            self._selected_index = 0

        screen_w = float(rl.get_screen_width())
        screen_h = float(rl.get_screen_height())
        scale = ui_scale(screen_w, screen_h)
        origin = ui_origin(screen_w, screen_h, scale)
        slide_x = run_mod_menu_panel_slide_x(self._timeline_ms, layout=self._layout)

        computed = run_mod_menu_compute_layout(
            self._layout,
            screen_w=screen_w,
            origin=origin,
            scale=scale,
            choice_count=len(choices),
            panel_slide_x=slide_x,
        )

        panel_tex = ctx.resources.texture(TextureId.UI_MENU_PANEL)
        draw_classic_menu_panel(
            panel_tex,
            dst=computed.panel.to_rl(),
            shadow=bool(ctx.shadows_enabled),
            trim_hardware=True,
        )
        # Not native: the trimmed-off hinge-cable decoration, reused here as a
        # visual connector back to the perk panel immediately to our left.
        # Scaled down so it bridges the (narrow) gap between the two panels
        # instead of stretching back into the perk panel's own face.
        draw_menu_panel_hardware(panel_tex, panel=computed.panel.to_rl(), scale=0.22 * scale)

        draw_ui_text(ctx.resources, _TITLE_TEXT, computed.title_pos, scale=scale, color=_TITLE_COLOR)

        for idx, choice in enumerate(choices):
            label = run_mod_choice_display_name(choice, violence_disabled=int(ctx.violence_disabled))
            item_pos = computed.list_pos.offset(dy=float(idx) * computed.list_step_y)
            rect = menu_item_hit_rect(ctx.resources, label, pos=item_pos, scale=scale)
            hovered = rect.contains(ctx.mouse) or (idx == self._selected_index)
            draw_menu_item(ctx.resources, label, pos=item_pos, scale=scale, hovered=hovered)

        selected = choices[self._selected_index]
        desc = run_mod_choice_display_description(selected, violence_disabled=int(ctx.violence_disabled))
        # Not native: most run-mod descriptions are one short line, but a
        # Wildcard-replaced slot shows a full perk description (2-3 sentences)
        # and needs to wrap to the panel's own width instead of running past
        # its right edge. Also clip to however many lines actually fit above
        # the Cancel button, so an especially long one doesn't draw over it.
        desc_lines = wrap_ui_text(ctx.resources, desc, max_width=computed.desc.w, scale=scale)
        line_h = ctx.resources.small_font.cell_size * scale
        max_lines = max(1, int(computed.desc.h // line_h)) if line_h > 0 else len(desc_lines)
        draw_ui_text(
            ctx.resources,
            "\n".join(desc_lines[:max_lines]),
            computed.desc.top_left,
            scale=scale,
            color=UI_TEXT_COLOR,
        )

        cancel_w = button_width(
            ctx.resources, self._cancel_button.label, scale=scale, force_wide=self._cancel_button.force_wide,
        )
        button_draw(
            ctx.resources,
            self._cancel_button,
            pos=computed.cancel_pos,
            width=cancel_w,
            scale=scale,
        )
