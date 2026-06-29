"""User-facing dataclasses for the bAInary lifting artifact.

The Pydantic schema in :mod:`bainary.lift.schema` is the JSON contract;
these dataclasses are the ergonomic Python API. Value objects
(:class:`BinaryInfo`, :class:`Section`, :class:`CallRef`, etc.) are
frozen so they can be safely shared. Compound objects
(:class:`Function`, :class:`BinaryArtifact`) are mutable so callers can
annotate, rename, or patch fields before re-serializing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import SchemaValidationError
from .schema import SCHEMA_VERSION, BinaryArtifactSchema


def _enum_str(v: Any) -> Any:
    """Return ``v.value`` if ``v`` is a StrEnum, otherwise ``v`` unchanged."""
    return getattr(v, "value", v)


@dataclass(frozen=True)
class BinaryInfo:
    path: str
    sha256: str
    format: str
    arch: str
    endianness: str
    entry_point: str
    base_address: str
    decompiler_version: str = ""


@dataclass(frozen=True)
class Section:
    name: str
    address: str
    size: int
    permissions: str


@dataclass(frozen=True)
class ImportRef:
    address: str
    name: str
    library: str


@dataclass(frozen=True)
class ExportRef:
    address: str
    name: str


@dataclass(frozen=True)
class StringRef:
    address: str
    value: str
    encoding: str


@dataclass(frozen=True)
class CallRef:
    address: str
    name: str
    is_external: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CallRef:
        return cls(
            address=d["address"],
            name=d["name"],
            is_external=d.get("is_external", False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "is_external": self.is_external,
        }


@dataclass(frozen=True)
class Local:
    name: str
    offset: int
    size: int
    type: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Local:
        return cls(
            name=d["name"],
            offset=d["offset"],
            size=d["size"],
            type=d["type"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": self.size,
            "type": self.type,
        }


@dataclass(frozen=True)
class Instruction:
    address: str
    bytes: str
    mnemonic: str
    operands: list[str] = field(default_factory=list)
    comment: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Instruction:
        return cls(
            address=d["address"],
            bytes=d["bytes"],
            mnemonic=d["mnemonic"],
            operands=list(d.get("operands", [])),
            comment=d.get("comment"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "bytes": self.bytes,
            "mnemonic": self.mnemonic,
            "operands": list(self.operands),
            "comment": self.comment,
        }


@dataclass(frozen=True)
class BasicBlock:
    address: str
    instructions: list[Instruction] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    terminator: str = "other"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BasicBlock:
        return cls(
            address=d["address"],
            instructions=[Instruction.from_dict(i) for i in d.get("instructions", [])],
            successors=list(d.get("successors", [])),
            terminator=_enum_str(d.get("terminator", "other")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "instructions": [i.to_dict() for i in self.instructions],
            "successors": list(self.successors),
            "terminator": self.terminator,
        }


@dataclass
class Cfg:
    nodes: list[str] = field(default_factory=list)
    edges: list[list[str]] = field(default_factory=list)


@dataclass
class StackFrame:
    size: int = 0
    locals: list[Local] = field(default_factory=list)


@dataclass
class Function:
    address: str
    name: str
    signature: str
    calling_convention: str
    size_bytes: int
    assembly: str
    is_thunk: bool = False
    basic_blocks: list[BasicBlock] = field(default_factory=list)
    cfg: Cfg = field(default_factory=Cfg)
    callers: list[CallRef] = field(default_factory=list)
    callees: list[CallRef] = field(default_factory=list)
    pseudocode: str | None = None
    pseudocode_error: str | None = None
    decompiler: str = "ghidra"
    stack_frame: StackFrame = field(default_factory=StackFrame)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Function:
        cfg_d = d.get("cfg") or {}
        sf_d = d.get("stack_frame") or {}
        return cls(
            address=d["address"],
            name=d["name"],
            signature=d["signature"],
            calling_convention=_enum_str(d["calling_convention"]),
            size_bytes=d["size_bytes"],
            assembly=d["assembly"],
            is_thunk=d.get("is_thunk", False),
            basic_blocks=[BasicBlock.from_dict(b) for b in d.get("basic_blocks", [])],
            cfg=Cfg(
                nodes=list(cfg_d.get("nodes", [])),
                edges=[list(e) for e in cfg_d.get("edges", [])],
            ),
            callers=[CallRef.from_dict(c) for c in d.get("callers", [])],
            callees=[CallRef.from_dict(c) for c in d.get("callees", [])],
            pseudocode=d.get("pseudocode"),
            pseudocode_error=d.get("pseudocode_error"),
            decompiler=d.get("decompiler", "ghidra"),
            stack_frame=StackFrame(
                size=sf_d.get("size", 0),
                locals=[Local.from_dict(loc) for loc in sf_d.get("locals", [])],
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "signature": self.signature,
            "calling_convention": self.calling_convention,
            "size_bytes": self.size_bytes,
            "is_thunk": self.is_thunk,
            "basic_blocks": [b.to_dict() for b in self.basic_blocks],
            "cfg": {
                "nodes": list(self.cfg.nodes),
                "edges": [list(e) for e in self.cfg.edges],
            },
            "callers": [c.to_dict() for c in self.callers],
            "callees": [c.to_dict() for c in self.callees],
            "assembly": self.assembly,
            "pseudocode": self.pseudocode,
            "pseudocode_error": self.pseudocode_error,
            "decompiler": self.decompiler,
            "stack_frame": {
                "size": self.stack_frame.size,
                "locals": [loc.to_dict() for loc in self.stack_frame.locals],
            },
        }


@dataclass
class BinaryArtifact:
    binary: BinaryInfo
    sections: list[Section] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    exports: list[ExportRef] = field(default_factory=list)
    strings: list[StringRef] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BinaryArtifact:
        try:
            schema = BinaryArtifactSchema.model_validate(d)
        except ValidationError as e:
            errs = e.errors()
            field_path = ".".join(str(p) for p in errs[0]["loc"]) if errs else ""
            raise SchemaValidationError(str(e), field=field_path) from e

        b = schema.binary
        return cls(
            binary=BinaryInfo(
                path=b.path,
                sha256=b.sha256,
                format=b.format.value,
                arch=b.arch.value,
                endianness=b.endianness.value,
                entry_point=b.entry_point,
                base_address=b.base_address,
                decompiler_version=b.decompiler_version,
            ),
            sections=[
                Section(
                    name=s.name,
                    address=s.address,
                    size=s.size,
                    permissions=s.permissions,
                )
                for s in schema.sections
            ],
            imports=[
                ImportRef(address=i.address, name=i.name, library=i.library)
                for i in schema.imports
            ],
            exports=[ExportRef(address=e.address, name=e.name) for e in schema.exports],
            strings=[
                StringRef(address=s.address, value=s.value, encoding=s.encoding.value)
                for s in schema.strings
            ],
            functions=[Function.from_dict(f.model_dump()) for f in schema.functions],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "binary": {
                "path": self.binary.path,
                "sha256": self.binary.sha256,
                "format": self.binary.format,
                "arch": self.binary.arch,
                "endianness": self.binary.endianness,
                "entry_point": self.binary.entry_point,
                "base_address": self.binary.base_address,
                "decompiler_version": self.binary.decompiler_version,
            },
            "sections": [
                {
                    "name": s.name,
                    "address": s.address,
                    "size": s.size,
                    "permissions": s.permissions,
                }
                for s in self.sections
            ],
            "imports": [
                {"address": i.address, "name": i.name, "library": i.library}
                for i in self.imports
            ],
            "exports": [{"address": e.address, "name": e.name} for e in self.exports],
            "strings": [
                {"address": s.address, "value": s.value, "encoding": s.encoding}
                for s in self.strings
            ],
            "functions": [f.to_dict() for f in self.functions],
        }

    def to_json(self, path: Path) -> None:
        validated = BinaryArtifactSchema.model_validate(self.to_dict())
        path.write_text(validated.model_dump_json(indent=2))

    @classmethod
    def from_json(cls, path: Path) -> BinaryArtifact:
        return cls.from_dict(json.loads(path.read_text()))
