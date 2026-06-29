"""Pydantic v2 models implementing the bAInary lifting JSON contract.

This module is the single source of truth for the schema. Downstream
subsystems (B, C, D, E) import these models to validate and parse the
JSON emitted by subsystem A.
"""
from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"
"""Current contract version. Bump on breaking changes."""

_HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def _validate_hex(value: str, field_name: str) -> str:
    if not _HEX_RE.match(value):
        raise ValueError(
            f"{field_name} must be a hex string like '0x401000', got {value!r}"
        )
    return value


class CallingConvention(StrEnum):
    cdecl = "cdecl"
    stdcall = "stdcall"
    fastcall = "fastcall"
    thiscall = "thiscall"
    unknown = "unknown"


class BinaryFormat(StrEnum):
    PE = "PE"
    ELF = "ELF"
    MACHO = "MACHO"


class Arch(StrEnum):
    x86 = "x86"
    x64 = "x64"
    arm = "arm"
    arm64 = "arm64"


class Endianness(StrEnum):
    little = "little"
    big = "big"


class Encoding(StrEnum):
    ascii = "ascii"
    utf8 = "utf8"
    utf16 = "utf16"


class Terminator(StrEnum):
    jmp = "jmp"
    cjmp = "cjmp"
    ret = "ret"
    call = "call"
    fall_through = "fall_through"
    other = "other"


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BinaryInfoSchema(_BaseModel):
    path: str
    sha256: str = Field(min_length=64, max_length=64)
    format: BinaryFormat
    arch: Arch
    endianness: Endianness
    entry_point: str
    base_address: str
    decompiler_version: str = ""

    @field_validator("entry_point", "base_address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class SectionSchema(_BaseModel):
    name: str
    address: str
    size: int = Field(ge=0)
    permissions: str

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class ImportRefSchema(_BaseModel):
    address: str
    name: str
    library: str

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class ExportRefSchema(_BaseModel):
    address: str
    name: str

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class StringRefSchema(_BaseModel):
    address: str
    value: str
    encoding: Encoding

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class CallRefSchema(_BaseModel):
    address: str
    name: str
    is_external: bool = False

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class InstructionSchema(_BaseModel):
    address: str
    bytes: str
    mnemonic: str
    operands: list[str] = Field(default_factory=list)
    comment: str | None = None

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class BasicBlockSchema(_BaseModel):
    address: str
    instructions: list[InstructionSchema] = Field(default_factory=list)
    successors: list[str] = Field(default_factory=list)
    terminator: Terminator

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")


class CfgSchema(_BaseModel):
    nodes: list[str] = Field(default_factory=list)
    edges: list[list[str]] = Field(default_factory=list)


class LocalSchema(_BaseModel):
    name: str
    offset: int
    size: int = Field(ge=0)
    type: str


class StackFrameSchema(_BaseModel):
    size: int = Field(ge=0)
    locals: list[LocalSchema] = Field(default_factory=list)


class FunctionSchema(_BaseModel):
    address: str
    name: str
    signature: str
    calling_convention: CallingConvention
    size_bytes: int = Field(ge=0)
    is_thunk: bool = False
    basic_blocks: list[BasicBlockSchema] = Field(default_factory=list)
    cfg: CfgSchema = Field(default_factory=CfgSchema)
    callers: list[CallRefSchema] = Field(default_factory=list)
    callees: list[CallRefSchema] = Field(default_factory=list)
    assembly: str
    pseudocode: str | None = None
    pseudocode_error: str | None = None
    decompiler: Literal["ghidra", "lief_capstone"] = "ghidra"
    stack_frame: StackFrameSchema = Field(default_factory=StackFrameSchema)  # type: ignore[arg-type]

    @field_validator("address")
    @classmethod
    def _check_hex(cls, v: str) -> str:
        return _validate_hex(v, "address")

    @field_validator("cfg")
    @classmethod
    def _cfg_nodes_are_hex(cls, v: CfgSchema) -> CfgSchema:
        for n in v.nodes:
            _validate_hex(n, "cfg.node")
        for edge in v.edges:
            if len(edge) != 2:
                raise ValueError(f"cfg edge must be [from, to], got {edge!r}")
            _validate_hex(edge[0], "cfg.edge[0]")
            _validate_hex(edge[1], "cfg.edge[1]")
        return v


class BinaryArtifactSchema(_BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    binary: BinaryInfoSchema
    sections: list[SectionSchema] = Field(default_factory=list)
    imports: list[ImportRefSchema] = Field(default_factory=list)
    exports: list[ExportRefSchema] = Field(default_factory=list)
    strings: list[StringRefSchema] = Field(default_factory=list)
    functions: list[FunctionSchema] = Field(default_factory=list)
