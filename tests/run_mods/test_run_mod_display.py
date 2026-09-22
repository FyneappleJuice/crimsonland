from __future__ import annotations

from crimson.perks import PerkId
from crimson.run_mods.display import run_mod_choice_display_description, run_mod_choice_display_name
from crimson.run_mods.ids import RunModId
from crimson.run_mods.state import RunModChoice, RunModChoiceKind


def test_plain_choice_uses_the_run_mod_s_own_strings() -> None:
    choice = RunModChoice(kind=RunModChoiceKind.RUN_MOD, run_mod_id=RunModId.FIRE_RATE)
    assert run_mod_choice_display_name(choice) == "Fire Rate"
    assert run_mod_choice_display_description(choice) == "+2% fire rate."


def test_perk_choice_uses_the_perk_s_own_strings() -> None:
    choice = RunModChoice(kind=RunModChoiceKind.PERK, perk_id=PerkId.FASTLOADER)
    assert run_mod_choice_display_name(choice) == "Fastloader"
    assert run_mod_choice_display_description(choice) == "Man, you sure know how to load a gun."


def test_upgraded_choice_scales_the_boost_up_and_the_penalty_down() -> None:
    # Bullet Damage's own benefit reads "+3%" - tripled should read "+9%".
    choice = RunModChoice(
        kind=RunModChoiceKind.UPGRADED_RUN_MOD,
        run_mod_id=RunModId.BULLET_DAMAGE,
        penalty_run_mod_id=RunModId.FIRE_RATE,
    )
    desc = run_mod_choice_display_description(choice)
    assert "+9% Bullet Damage" in desc
    # Fire Rate's own benefit reads "+2%" (a cooldown cut framed as a rate
    # increase) - inverted as a penalty it must read as a NEGATIVE fire rate
    # change, not a positive one, even though the underlying StatMod value
    # it's built from is itself already negative.
    assert "-2% Fire Rate" in desc


def test_upgraded_choice_penalty_inverts_an_already_negative_benefit_correctly() -> None:
    # Reload Speed's own benefit reads "-3%" (less time is the win) -
    # inverted as a penalty it must read as a POSITIVE (worse) number.
    choice = RunModChoice(
        kind=RunModChoiceKind.UPGRADED_RUN_MOD,
        run_mod_id=RunModId.FIRE_RATE,
        penalty_run_mod_id=RunModId.RELOAD_SPEED,
    )
    desc = run_mod_choice_display_description(choice)
    assert "+3% Reload Speed" in desc
