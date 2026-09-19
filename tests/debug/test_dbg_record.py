from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import crimson.dbg.record as dbg_record
from crimson.dbg.canonical_channels import (
    EntitySamplesSnapshot,
    SimStateSnapshot,
    SnapshotBonusTimers,
    SnapshotGameplay,
    SnapshotPlayer,
    SnapshotVec2,
    SnapshotWeapon,
    bonus_timer_ms,
)
from crimson.dbg.schema import TRACE_SCHEMA_VERSION
from crimson.dbg.trace import load_trace
from crimson.game_modes import GameMode
from crimson.persistence.save_status import GameStatusData
from crimson.replay.checkpoints import (
    ReplayCheckpoint,
    ReplayCheckpointVec2,
    ReplayEventSummary,
    ReplayPerkSnapshot,
    ReplayPlayerCheckpoint,
)
from crimson.replay.types import Replay, ReplayHeader, ReplayTick
from crimson.weapons import WeaponId


def test_bonus_timer_ms_matches_frida_nearest_millisecond_encoding() -> None:
    assert bonus_timer_ms(8.811999320983887) == 8812
    assert bonus_timer_ms(0.0005) == 1
    assert bonus_timer_ms(-1.0) == 0


def test_canonical_elapsed_ms_uses_unscaled_replay_clock() -> None:
    replay = Replay(
        header=ReplayHeader(
            game_mode_id=GameMode.SURVIVAL,
            seed=0x1234,
            status=GameStatusData(),
        ),
        ticks=[
            ReplayTick(dt=0.1, inputs=[]),
            ReplayTick(dt=0.09, inputs=[]),
            ReplayTick(dt=0.087, inputs=[]),
        ],
    )

    assert dbg_record._canonical_elapsed_ms_by_tick(replay) == [100, 190, 277]


def test_record_replay_to_trace_records_via_python_impl(monkeypatch, tmp_path: Path) -> None:
    replay_path = tmp_path / "sample.crd"
    out_path = tmp_path / "sample.cdt"
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_python(
        *,
        replay_path: Path,
        out_path: Path,
    ) -> object:
        captured["replay_path"] = replay_path
        captured["out_path"] = out_path
        return sentinel

    monkeypatch.setattr(dbg_record, "_record_replay_to_trace_python", _fake_python)

    result = dbg_record.record_replay_to_trace(
        replay_path=replay_path,
        out_path=out_path,
    )

    assert result is sentinel
    assert captured["replay_path"] == replay_path
    assert captured["out_path"] == out_path


def test_record_replay_to_trace_python_writes_unattributed_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    replay_path = tmp_path / "sample.crd"
    replay_path.write_bytes(b"fake")
    replay = Replay(
        header=ReplayHeader(
            game_mode_id=GameMode.SURVIVAL,
            seed=0x1234,
            status=GameStatusData(),
        ),
        ticks=[ReplayTick(dt=0.016, inputs=[[0.0, 0.0, 0.0, 0.0, 0]])],
    )

    class _FakeDriver:
        def build_checkpoint(self, *, tick_result) -> ReplayCheckpoint:
            return ReplayCheckpoint(
                tick_index=int(tick_result.source_tick.tick_index),
                rng_state=0,
                elapsed_ms=0,
                score_xp=0,
                kills=0,
                creature_count=0,
                perk_pending=0,
                players=[
                    ReplayPlayerCheckpoint(
                        pos=ReplayCheckpointVec2(0.0, 0.0),
                        health=100.0,
                        weapon_id=WeaponId.PISTOL,
                        ammo=0.0,
                        experience=0,
                        level=1,
                    ),
                ],
                bonus_timers={},
                deaths=[],
                perk=ReplayPerkSnapshot(
                    pending_count=0,
                    choices_dirty=False,
                    choices=[0] * 7,
                    player_nonzero_counts=[[]],
                ),
                events=ReplayEventSummary(
                    hit_count=0,
                    pickup_count=0,
                    sfx_count=0,
                    sfx_head=[],
                    hit_head=[],
                ),
                tutorial=None,
                typo=None,
            )

        def run(self, *, observer):
            tick_result = SimpleNamespace(source_tick=SimpleNamespace(tick_index=0))
            world = SimpleNamespace(
                state=SimpleNamespace(
                    time_scale_active=False,
                    bonuses=SimpleNamespace(reflex_boost=0.0),
                ),
            )
            observer.before_tick(0, world, 0.016)
            observer.after_tick(tick_result, world)
            observer.rng_trace(
                tick_result,
                ((0x90ABCDEF, 23203, 0x5AA3B0F6, None),),
            )
            return SimpleNamespace()

    monkeypatch.setattr(dbg_record, "load_replay_file", lambda _path: replay)
    monkeypatch.setattr(dbg_record, "build_verify_playback_driver", lambda *_args, **_kwargs: _FakeDriver())
    monkeypatch.setattr(
        dbg_record,
        "_entity_samples_for_world",
        lambda *_args, **_kwargs: EntitySamplesSnapshot(
            creatures=[],
            projectiles=[],
            secondary_projectiles=[],
            bonuses=[],
        ),
    )
    monkeypatch.setattr(
        dbg_record,
        "_sim_state_from_world",
        lambda *_args, **_kwargs: SimStateSnapshot(
            gameplay=SnapshotGameplay(
                mode_id=int(GameMode.SURVIVAL),
                quest_stage_major=-1,
                quest_stage_minor=-1,
                perk_pending_count=0,
                perk_choices_dirty=False,
                bonus_timers=SnapshotBonusTimers(
                    weapon_power_up_ms=0,
                    reflex_boost_ms=0,
                    energizer_ms=0,
                    double_experience_ms=0,
                    freeze_ms=0,
                ),
            ),
            players=[
                SnapshotPlayer(
                    index=0,
                    pos=SnapshotVec2(x=0.0, y=0.0),
                    heading=0.0,
                    move_speed=0.0,
                    move_phase=0.0,
                    aim=SnapshotVec2(x=0.0, y=0.0),
                    aim_heading=0.0,
                    health=100.0,
                    weapon=SnapshotWeapon(
                        weapon_id=int(WeaponId.PISTOL),
                        ammo=0.0,
                        clip_size=0,
                        reload_active=False,
                        reload_timer=0.0,
                        reload_timer_max=0.0,
                        shot_cooldown=0.0,
                    ),
                    experience=0,
                    level=1,
                ),
            ],
        ),
    )

    summary = dbg_record._record_replay_to_trace_python(
        replay_path=replay_path,
        out_path=tmp_path / "sample.cdt",
    )

    assert summary.meta.trace_schema_version == TRACE_SCHEMA_VERSION
    meta, ticks, footer = load_trace(tmp_path / "sample.cdt")
    assert meta.trace_schema_version == TRACE_SCHEMA_VERSION
    assert meta.status == replay.header.status
    assert footer.tick_count == 1
    assert ticks[0].channels.rng_stream[0].caller is None
    assert len(ticks[0].channels.timing_samples) == 1
    assert ticks[0].channels.timing_samples[0].phase == "gpur_enter"
