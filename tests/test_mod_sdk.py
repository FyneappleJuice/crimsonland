from __future__ import annotations

import struct
from pathlib import Path

from crimson.match import (
    IMAGE_REL_I386_REL32,
    LoadedImage,
    ObjectFunction,
    ObjectRelocationReference,
)
from crimson.mod_sdk import (
    DEFAULT_MOD_SDK_MANIFEST,
    ModSdkOracleFunction,
    ModSdkOracleReport,
    _find_masked_fingerprint_hits,
    _resolve_oracle_addresses,
    load_mod_sdk_manifest,
    mod_sdk_oracle_report_payload,
    render_mod_sdk_oracle_report,
)


def test_mod_sdk_manifest_pins_source_binary_pair() -> None:
    payload = load_mod_sdk_manifest(DEFAULT_MOD_SDK_MANIFEST)

    assert payload["package"]["release"] == "2003-08-14"
    assert payload["package"]["archive"]["sha256"] == (
        "f81cc70ebe29cf9576b251e8723802dedd7abdd7b6b00a8d15c503ed8ceb786c"
    )
    projects = {project["name"]: project for project in payload["projects"]}
    assert projects["cl_nullmod"]["compiler"]["build"] == 9044
    assert projects["cl_crimsonroks"]["rich_records"][0] == {
        "product_id": 49,
        "build": 9044,
        "count": 2,
    }
    assert projects["cl_crimsonroks"]["oracle"] == {
        "source": "cl_crimsonroks/src/r_roks.cpp",
        "symbol_prefix": "?r",
        "expected_functions": 25,
    }
    assert "Linux ports" in payload["calibration"]["excluded_claims"][-1]


def test_sdk_oracle_fingerprint_masks_linker_words() -> None:
    function = ObjectFunction(
        name="?example@@YAXXZ",
        data=b"\x55\x8b\xec\xe8\x00\x00\x00\x00\xc3",
        relocation_offsets=frozenset({4}),
        relocation_references=(
            ObjectRelocationReference(
                offset=4,
                symbol_name="?callee@@YAXXZ",
                key=None,
                explained=False,
                relocation_type=IMAGE_REL_I386_REL32,
            ),
        ),
    )
    segment = (
        b"\x90"
        + b"\x55\x8b\xec\xe8\x11\x22\x33\x44\xc3"
        + b"\x90"
        + b"\x55\x8b\xec\xe8\xaa\xbb\xcc\xdd\xc3"
    )

    assert _find_masked_fingerprint_hits(function, ((0x1000, segment),)) == (
        0x1001,
        0x100B,
    )


def test_sdk_oracle_uses_caller_xref_to_split_identical_bodies() -> None:
    callee_symbol = "?callee@@YAXXZ"
    caller = ObjectFunction(
        name="?caller@@YAXXZ",
        data=b"\xe8\x00\x00\x00\x00\xc3",
        relocation_offsets=frozenset({1}),
        relocation_references=(
            ObjectRelocationReference(
                offset=1,
                symbol_name=callee_symbol,
                key=None,
                explained=False,
                relocation_type=IMAGE_REL_I386_REL32,
            ),
        ),
    )
    callee = ObjectFunction(name=callee_symbol, data=b"\xc3", relocation_offsets=frozenset())
    mapped = bytearray(0x100)
    caller_va = 0x1010
    callee_va = 0x1040
    struct.pack_into("<i", mapped, caller_va - 0x1000 + 1, callee_va - (caller_va + 5))
    image = LoadedImage(mapped=bytes(mapped), image_base=0x1000, size_of_image=len(mapped))

    resolved, evidence = _resolve_oracle_addresses(
        {caller.name: caller, callee.name: callee},
        {caller.name: (caller_va,), callee.name: (0x1030, callee_va)},
        image,
    )

    assert resolved[callee.name] == callee_va
    assert evidence[callee.name] == "masked-fingerprint+caller-xref"


def test_sdk_oracle_report_calls_manifest_selection_authored_functions(tmp_path: Path) -> None:
    function = ModSdkOracleFunction(
        name="rExample",
        symbol="?rExample@@YAXXZ",
        size=1,
        instructions=1,
        target_instructions=1,
        target_va=0x10001000,
        fingerprint_candidates=(0x10001000,),
        evidence="masked-fingerprint",
        normalized_ratio=1.0,
    )
    report = ModSdkOracleReport(
        source=tmp_path,
        source_kind="directory",
        release="2003-08-14",
        archive_sha256="00" * 32,
        project="example",
        source_path="example.cpp",
        compiler_product_id=49,
        compiler_build=9044,
        expected_functions=1,
        provenance_checks=1,
        functions=(function,),
    )

    payload = mod_sdk_oracle_report_payload(report)

    assert payload["summary"]["authored_functions"] == 1
    assert "application_functions" not in payload["summary"]
    assert "authored-functions=1/1" in render_mod_sdk_oracle_report(report)
