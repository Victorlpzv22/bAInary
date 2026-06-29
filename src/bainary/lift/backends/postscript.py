"""Jython 2.7 postScript run inside Ghidra's analyzeHeadless JVM.

The string ``POSTSCRIPT_SOURCE`` is written to a temp file by
:class:`bainary.lift.backends.ghidra_headless.GhidraHeadlessBackend` and
passed via ``-postScript``. It receives two globals from the backend via
``-postScript`` arg parsing (we pass them in via ``sys.argv``):

  sys.argv[1] = absolute path to write the JSON output to.

It produces a JSON object matching :class:`BinaryArtifactSchema`.

This is the ONLY file in the project that uses the Ghidra Java API.
Keeping the Jython legacy contained here lets the rest of the codebase
stay on modern Python 3.11+.
"""

from __future__ import annotations

POSTSCRIPT_SOURCE = r'''# -*- coding: utf-8 -*-
"""
Jython 2.7 postScript for bAInary subsystem A.

Usage (driven by GhidraHeadlessBackend):
    analyzeHeadless <project> -import <binary> -postScript this_file.py \
        -postScriptArgs <output_json_path>
"""

import json
import os
import sys
import traceback

from ghidra.app.decompiler import DecompInterface, DecompileOptions
from ghidra.program.model.block import BasicBlockModel
from ghidra.util.task import ConsoleTaskMonitor


OUTPUT_PATH = os.environ.get("BAINARY_OUTPUT_JSON")
if not OUTPUT_PATH:
    if len(sys.argv) > 1:
        OUTPUT_PATH = sys.argv[1]
    else:
        OUTPUT_PATH = "/tmp/bainary_postscript_out.json"


def _addr(a):
    """Address -> hex string '0x...'."""
    if a is None:
        return None
    return "0x%x" % a.getOffset()


def _endianness(language):
    return "big" if language.isBigEndian() else "little"


def _arch(language):
    proc = str(language.getProcessor())
    sz = language.getLanguageDescription().getSize()  # in bits
    if sz == 64:
        return "x64"
    if sz == 32:
        return "x86"
    return proc  # fall back to processor name


def _format(program):
    """Detect 'PE' or 'ELF' from the loaded binary's executable format."""
    fmt = str(program.getExecutableFormat()).upper()
    if "PE" in fmt or "PORTABLE EXECUTABLE" in fmt:
        return "PE"
    if "ELF" in fmt:
        return "ELF"
    return "UNKNOWN"


def _deref_string(data):
    """Best-effort: try to read a NUL-terminated ASCII/UTF-8 string at addr."""
    try:
        s = data.getString()
        if s is not None:
            return str(s)
    except Exception:
        pass
    return None


def _emit_function(func, decomp, listing, blockModel, refMgr, monitor):
    func_data = {
        "address": _addr(func.getEntryPoint()),
        "name": func.getName(),
        "signature": str(func.getSignature()),
        "calling_convention": func.getCallingConventionName() or "unknown",
        "size_bytes": int(func.getBody().getNumAddresses()),
        "is_thunk": bool(func.isThunk()),
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": [],
        "assembly": "",
        "pseudocode": None,
        "pseudocode_error": None,
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    }

    # Assembly listing
    asm_lines = []
    inst_iter = listing.getInstructions(func.getBody(), True)
    while inst_iter.hasNext():
        ins = inst_iter.next()
        try:
            operands = [str(o) for o in ins.getOpObjects(0)]  # 0 = first operand index (Jython signature)
        except Exception:
            operands = []
        asm_lines.append("%s %s" % (ins.toString(), " ".join(operands)))
    func_data["assembly"] = "\n".join(asm_lines)

    # Basic blocks + CFG
    try:
        nodes_set = set()
        edges = []
        block_iter = blockModel.getCodeBlocksContaining(func.getBody(), monitor)
        while block_iter.hasNext():
            block = block_iter.next()
            ba = _addr(block.getFirstStartAddress())
            if ba is None:
                continue
            nodes_set.add(ba)
            for d in block.getDestinations(monitor):
                da = _addr(d.getDestinationAddress())
                if da is not None:
                    edges.append([ba, da])
        func_data["cfg"]["nodes"] = sorted(nodes_set)
        func_data["cfg"]["edges"] = edges
    except Exception as e:
        func_data["pseudocode_error"] = "CFG extraction failed: %s" % e

    # Basic blocks in detail
    try:
        block_iter = blockModel.getCodeBlocksContaining(func.getBody(), monitor)
        while block_iter.hasNext():
            block = block_iter.next()
            baddr = _addr(block.getFirstStartAddress())
            if baddr is None:
                continue
            instrs = []
            ins_iter = listing.getInstructions(block, True)
            while ins_iter.hasNext():
                ins = ins_iter.next()
                try:
                    operands = [str(o) for o in ins.getOpObjects(0)]
                except Exception:
                    operands = []
                instrs.append({
                    "address": _addr(ins.getAddress()),
                    "bytes": " ".join("%02x" % b for b in ins.getBytes().getValue() or []),
                    "mnemonic": str(ins.getMnemonicString()),
                    "operands": operands,
                    "comment": None,
                })
            succs = [_addr(d.getDestinationAddress()) for d in block.getDestinations(monitor)]
            succs = [s for s in succs if s is not None]
            # Heuristic terminator
            last = instrs[-1]["mnemonic"] if instrs else ""
            term_map = {
                "jmp": "jmp", "je": "cjmp", "jne": "cjmp", "jg": "cjmp",
                "jge": "cjmp", "jl": "cjmp", "jle": "cjmp", "ja": "cjmp",
                "jae": "cjmp", "jb": "cjmp", "jbe": "cjmp", "ret": "ret",
                "call": "call", "hlt": "ret",
            }
            term = term_map.get(last, "other")
            func_data["basic_blocks"].append({
                "address": baddr,
                "instructions": instrs,
                "successors": succs,
                "terminator": term,
            })
    except Exception as e:
        print("WARN: basic block extraction failed for %s: %s" % (func.getName(), e))

    # Decompile
    try:
        results = decomp.decompileFunction(func, 60, monitor)
        if results is not None and results.decompileCompleted():
            decomp_fn = results.getDecompiledFunction()
            if decomp_fn is not None:
                func_data["pseudocode"] = decomp_fn.getC()
            else:
                func_data["pseudocode_error"] = "no decompiled function"
        else:
            msg = results.getErrorMessage() if results is not None else "no results"
            func_data["pseudocode_error"] = msg or "decompile failed"
    except Exception as e:
        func_data["pseudocode_error"] = "decompile exception: %s" % e

    # Callees
    try:
        for callee in func.getCalledFunctions(monitor):
            func_data["callees"].append({
                "address": _addr(callee.getEntryPoint()),
                "name": callee.getName(),
                "is_external": bool(callee.isExternal()),
            })
    except Exception as e:
        print("WARN: callee extraction failed for %s: %s" % (func.getName(), e))

    # Callers
    try:
        refs = refMgr.getReferencesTo(func.getEntryPoint())
        for ref in refs:
            caller_func = func.getProgram().getFunctionManager().getFunctionContaining(
                ref.getFromAddress()
            )
            if caller_func is not None:
                func_data["callers"].append({
                    "address": _addr(caller_func.getEntryPoint()),
                    "name": caller_func.getName(),
                })
    except Exception as e:
        print("WARN: caller extraction failed for %s: %s" % (func.getName(), e))

    # Stack frame + locals
    try:
        frame = func.getStackFrame()
        if frame is not None:
            func_data["stack_frame"]["size"] = int(frame.getFrameSize())
        for var in func.getLocalVariables():
            func_data["stack_frame"]["locals"].append({
                "name": var.getName(),
                "offset": int(var.getStackOffset()),
                "size": int(var.getLength()),
                "type": str(var.getDataType()),
            })
    except Exception as e:
        print("WARN: stack frame extraction failed for %s: %s" % (func.getName(), e))

    return func_data


def _emit_binary_metadata(program):
    image_base = program.getImageBase()
    # entry point: prefer symbol-table external entry, fall back to min address
    entry = None
    sym_iter = program.getSymbolTable().getExternalEntryPointIterator()
    if sym_iter.hasNext():
        entry = sym_iter.next()
    if entry is None:
        # fall back: look up "entry" symbol
        es = program.getSymbolTable().getSymbols("entry")
        if es.hasNext():
            entry = es.next().getAddress()
    if entry is None:
        entry = program.getMinAddress()

    binary = {
        "path": program.getExecutablePath(),
        "sha256": "",  # filled in by the Python wrapper (it has the file)
        "format": _format(program),
        "arch": _arch(program.getLanguage()),
        "endianness": _endianness(program.getLanguage()),
        "entry_point": _addr(entry),
        "base_address": _addr(image_base),
    }
    return binary


def _emit_sections(program):
    out = []
    memory = program.getMemory()
    for block in memory.getBlocks():
        perms = []
        if block.isRead():
            perms.append("r")
        if block.isWrite():
            perms.append("w")
        if block.isExecute():
            perms.append("x")
        out.append({
            "name": block.getName(),
            "address": _addr(block.getStart()),
            "size": int(block.getSize()),
            "permissions": "".join(perms) or "-",
        })
    return out


def _emit_imports(program):
    out = []
    sym_tab = program.getSymbolTable()
    for sym in sym_tab.getExternalSymbols():
        # Some symbols returned by getExternalSymbols() are not actually
        # external in the Jython API (e.g. FunctionSymbol lacks
        # getExternalLocation). Filter defensively.
        if not sym.isExternal():
            continue
        try:
            loc = sym.getExternalLocation()
        except Exception:
            loc = None
        lib = ""
        if loc is not None:
            try:
                lib = str(loc.getLibraryName() or "")
            except Exception:
                pass
        out.append({
            "address": _addr(sym.getAddress()),
            "name": sym.getName(),
            "library": lib,
        })
    return out


def _emit_exports(program):
    out = []
    sym_tab = program.getSymbolTable()
    # getLabelOrFunctionSymbols takes (Namespace, boolean) in this Ghidra version.
    try:
        iter_syms = sym_tab.getLabelOrFunctionSymbols(None, True)
    except TypeError:
        try:
            iter_syms = sym_tab.getLabelOrFunctionSymbols(None, None, True)
        except TypeError:
            iter_syms = []
    for sym in iter_syms:
        if sym.isExternal():
            continue
        out.append({"address": _addr(sym.getAddress()), "name": sym.getName()})
    return out


def _emit_strings(program):
    """Defined-string locations (not data in .rodata sections necessarily)."""
    out = []
    listing = program.getListing()
    data_iter = listing.getDefinedData(True)
    while data_iter.hasNext():
        d = data_iter.next()
        try:
            dt = d.getDataType()
            name = dt.getName().lower() if dt is not None else ""
            if "string" not in name and "char" not in name:
                continue
            val = d.getValue()
            if val is None:
                continue
            text = str(val)
            if not text or len(text) < 1:
                continue
            enc = "utf8"
            try:
                text.encode("ascii")
                enc = "ascii"
            except UnicodeEncodeError:
                pass
            out.append({
                "address": _addr(d.getAddress()),
                "value": text,
                "encoding": enc,
            })
        except Exception:
            continue
    return out


def main():
    monitor = ConsoleTaskMonitor()
    program = currentProgram  # noqa: F821 — provided by analyzeHeadless
    listing = program.getListing()
    refMgr = program.getReferenceManager()
    blockModel = BasicBlockModel(program)

    decomp = DecompInterface()
    decomp.openProgram(program)
    decomp.setOptions(DecompileOptions())

    artifact = {
        "schema_version": "1.0",
        "binary": _emit_binary_metadata(program),
        "sections": _emit_sections(program),
        "imports": _emit_imports(program),
        "exports": _emit_exports(program),
        "strings": _emit_strings(program),
        "functions": [],
    }

    fm = program.getFunctionManager()
    funcs = fm.getFunctions(True)
    while funcs.hasNext():
        func = funcs.next()
        try:
            artifact["functions"].append(
                _emit_function(func, decomp, listing, blockModel, refMgr, monitor)
            )
        except Exception as e:
            # Per-function failure: emit a stub so the rest of the artifact
            # is preserved.
            print("ERROR processing function %s: %s\n%s" % (
                func.getName(), e, traceback.format_exc()
            ))
            artifact["functions"].append({
                "address": _addr(func.getEntryPoint()),
                "name": func.getName(),
                "signature": str(func.getSignature()),
                "calling_convention": "unknown",
                "size_bytes": 0,
                "is_thunk": bool(func.isThunk()),
                "basic_blocks": [],
                "cfg": {"nodes": [], "edges": []},
                "callers": [],
                "callees": [],
                "assembly": "",
                "pseudocode": None,
                "pseudocode_error": "postScript error: %s" % e,
                "decompiler": "ghidra",
                "stack_frame": {"size": 0, "locals": []},
            })

    # Decompiler must be disposed
    try:
        decomp.dispose()
    except Exception:
        pass

    # Write output
    with open(OUTPUT_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
    print("bAInary postScript wrote %d functions to %s" % (
        len(artifact["functions"]), OUTPUT_PATH
    ))


main()
'''
