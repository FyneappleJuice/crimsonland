from __future__ import annotations

import json
import re
from pathlib import Path

import msgspec

from ..replay.checkpoints import (
    ReplayCheckpoint,
    ReplayDeathLedgerEntry,
    ReplayEventSummary,
    ReplayPerkSnapshot,
    ReplayPlayerCheckpoint,
)
from ..replay.types import ReplayTick
from . import frida_finalize as frida_format
from .canonical_channels import (
    BonusEntitySample,
    CreatureEntitySample,
    EntitySamplesSnapshot,
    ProjectileEntitySample,
    ReplayInputSample,
    ReplayStepSnapshot,
    SecondaryProjectileEntitySample,
    SnapshotBonusTimers,
    SnapshotPlayer,
    SnapshotWeapon,
    TimingSampleRow,
)
from .frida_finalize import FRIDA_CAPTURE_FORMAT_VERSION, FRIDA_RUNTIME_VERSION

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TICK_BOUNDARY_FIELDS = ("dt", "inputs", "prelude", "postlude", "commands")


def _field_names(struct_type: type[msgspec.Struct]) -> tuple[str, ...]:
    return tuple(field.name for field in msgspec.structs.fields(struct_type))


def _capture_field_sets() -> dict[str, tuple[str, ...]]:
    tagged: dict[str, type[msgspec.Struct]] = {
        "session_start": frida_format._SessionStartRow,
        "run_start": frida_format._RunStartRow,
        "tick": frida_format._TickRow,
        "run_end": frida_format._RunEndRow,
        "run_error": frida_format._RunErrorRow,
        "error": frida_format._ErrorRow,
    }
    nested: dict[str, type[msgspec.Struct]] = {
        "session_start.config": frida_format._SessionConfigRow,
        "session_start.session_fingerprint": frida_format._SessionFingerprintRow,
        "run_start.settings": frida_format._RunSettingsRow,
        "run_start.settings.status": frida_format._CaptureGameStatusRow,
        "run_start.pool_residue[]": frida_format._CapturePoolResidueRow,
        "tick.evidence": frida_format._CaptureTickEvidence,
        "tick.evidence.checkpoint_private": frida_format._CaptureCheckpointEvidence,
        "tick.evidence.checkpoint_private.events": frida_format._CaptureCheckpointEventEvidence,
        "tick.evidence.clocks": frida_format._CaptureClockEvidence,
        "tick.channels": frida_format._TickChannels,
        "tick.channels.replay_step": ReplayStepSnapshot,
        "tick.channels.replay_step.inputs[]": ReplayInputSample,
        "tick.channels.checkpoint": ReplayCheckpoint,
        "tick.channels.checkpoint.players[]": ReplayPlayerCheckpoint,
        "tick.channels.checkpoint.deaths[]": ReplayDeathLedgerEntry,
        "tick.channels.checkpoint.perk": ReplayPerkSnapshot,
        "tick.channels.checkpoint.events": ReplayEventSummary,
        "tick.channels.sim_state": frida_format._CaptureSimStateSnapshot,
        "tick.channels.sim_state.gameplay": frida_format._CaptureSnapshotGameplay,
        "tick.channels.sim_state.gameplay.bonus_timers": SnapshotBonusTimers,
        "tick.channels.sim_state.players[]": SnapshotPlayer,
        "tick.channels.sim_state.players[].weapon": SnapshotWeapon,
        "tick.channels.entity_samples": EntitySamplesSnapshot,
        "tick.channels.entity_samples.creatures[]": CreatureEntitySample,
        "tick.channels.entity_samples.projectiles[]": ProjectileEntitySample,
        "tick.channels.entity_samples.secondary_projectiles[]": SecondaryProjectileEntitySample,
        "tick.channels.entity_samples.bonuses[]": BonusEntitySample,
        "tick.channels.rng_stream[]": frida_format._CaptureRngStreamRow,
        "tick.channels.timing_samples[]": TimingSampleRow,
        "tick.rng_outside_before": frida_format._OutsideRngBag,
        "tick.rng_outside_before.head[]": frida_format._OutsideRngHeadRow,
        "run_end.rng_outside_tail": frida_format._OutsideRngBag,
        "run_end.rng_outside_tail.head[]": frida_format._OutsideRngHeadRow,
    }
    return {
        **{path: ("event", *_field_names(struct_type)) for path, struct_type in tagged.items()},
        **{path: _field_names(struct_type) for path, struct_type in nested.items()},
    }


def _source_int(
    source: str,
    *,
    pattern: str,
    label: str,
    errors: list[str],
) -> int | None:
    match = re.search(pattern, source, flags=re.MULTILINE)
    if match is None:
        errors.append(f"{label} declaration is missing")
        return None
    return int(match.group(1))


def format_contract_errors() -> list[str]:
    """Return every current-format wiring mismatch across Python and Frida."""

    errors: list[str] = []
    for label, struct_type in (
        ("Python ReplayTick", ReplayTick),
        ("Python ReplayStepSnapshot", ReplayStepSnapshot),
    ):
        fields = _field_names(struct_type)
        if fields != _TICK_BOUNDARY_FIELDS:
            errors.append(f"{label} fields are {fields!r}, expected {_TICK_BOUNDARY_FIELDS!r}")

    frida_source = (_REPO_ROOT / "scripts" / "frida" / "gameplay_diff_capture.js").read_text()
    frida_version = _source_int(
        frida_source,
        pattern=r"^const CAPTURE_FORMAT_VERSION = (\d+);$",
        label="Frida capture version",
        errors=errors,
    )
    if frida_version is not None and frida_version != int(FRIDA_CAPTURE_FORMAT_VERSION):
        errors.append(
            f"Frida capture version is {frida_version}, expected {int(FRIDA_CAPTURE_FORMAT_VERSION)}",
        )
    runtime_match = re.search(
        r'^const REQUIRED_FRIDA_VERSION = "([^"]+)";$',
        frida_source,
        flags=re.MULTILINE,
    )
    if runtime_match is None:
        errors.append("Frida runtime version declaration is missing")
    elif runtime_match.group(1) != FRIDA_RUNTIME_VERSION:
        errors.append(
            f"Frida runtime version is {runtime_match.group(1)!r}, expected {FRIDA_RUNTIME_VERSION!r}",
        )

    field_sets_match = re.search(
        r"// BEGIN CAPTURE_FIELD_SETS\nconst CAPTURE_FIELD_SETS = (?P<body>\{.*?\});\n// END CAPTURE_FIELD_SETS",
        frida_source,
        flags=re.DOTALL,
    )
    if field_sets_match is None:
        errors.append("Frida capture field-set manifest is missing")
    else:
        try:
            raw_field_sets = json.loads(field_sets_match.group("body"))
        except json.JSONDecodeError as exc:
            errors.append(f"Frida capture field-set manifest is invalid JSON: {exc}")
        else:
            expected_field_sets = _capture_field_sets()
            if set(raw_field_sets) != set(expected_field_sets):
                errors.append(
                    "Frida capture field-set paths differ: "
                    f"actual={sorted(raw_field_sets)!r}, expected={sorted(expected_field_sets)!r}",
                )
            for path in sorted(set(raw_field_sets) & set(expected_field_sets)):
                actual_fields = tuple(str(field) for field in raw_field_sets[path])
                expected_fields = expected_field_sets[path]
                if len(actual_fields) != len(set(actual_fields)) or set(actual_fields) != set(expected_fields):
                    errors.append(
                        f"Frida {path} fields are {actual_fields!r}, expected {expected_fields!r}",
                    )
    frida_step = re.search(
        r"replay_step:\s*\{(?P<body>.*?)^\s{8}\},$",
        frida_source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if frida_step is None:
        errors.append("Frida replay_step declaration is missing")
    else:
        frida_fields = tuple(
            re.findall(
                r"^\s{10}(dt|inputs|prelude|postlude|commands):",
                frida_step.group("body"),
                flags=re.MULTILINE,
            ),
        )
        if frida_fields != _TICK_BOUNDARY_FIELDS:
            errors.append(f"Frida replay_step fields are {frida_fields!r}, expected {_TICK_BOUNDARY_FIELDS!r}")

    return errors
