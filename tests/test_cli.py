import json

from typer.testing import CliRunner

from bainary.lift.cli import app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_cli_lift_writes_json(tmp_path, monkeypatch):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    out_json = tmp_path / "out.json"

    from bainary.lift import artifact as artifact_mod

    def fake_lift(path, **kwargs):
        d = {
            "schema_version": "1.0",
            "binary": {
                "path": str(path), "sha256": "ab" * 32,
                "format": "ELF", "arch": "x64", "endianness": "little",
                "entry_point": "0x400000", "base_address": "0x400000",
            },
            "sections": [], "imports": [], "exports": [], "strings": [], "functions": [],
        }
        return artifact_mod.BinaryArtifact.from_dict(d)

    monkeypatch.setattr("bainary.lift.cli.lift", fake_lift)

    runner = CliRunner()
    result = runner.invoke(app, [str(binary), "-o", str(out_json)])
    assert result.exit_code == 0, result.stdout
    assert out_json.exists()
    loaded = json.loads(out_json.read_text())
    assert loaded["binary"]["format"] == "ELF"


def test_cli_no_cache_flag(tmp_path, monkeypatch):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    out_json = tmp_path / "out.json"

    from bainary.lift import artifact as artifact_mod
    calls = []

    def fake_lift(path, **kwargs):
        calls.append(kwargs.get("use_cache"))
        d = {
            "schema_version": "1.0",
            "binary": {
                "path": str(path), "sha256": "ab" * 32,
                "format": "ELF", "arch": "x64", "endianness": "little",
                "entry_point": "0x400000", "base_address": "0x400000",
            },
            "sections": [], "imports": [], "exports": [], "strings": [], "functions": [],
        }
        return artifact_mod.BinaryArtifact.from_dict(d)

    monkeypatch.setattr("bainary.lift.cli.lift", fake_lift)

    runner = CliRunner()
    result = runner.invoke(app, [str(binary), "-o", str(out_json), "--no-cache"])
    assert result.exit_code == 0, result.stdout
    assert calls == [False]


def test_cli_unsupported_format_exits_nonzero(tmp_path):
    binary = tmp_path / "x.macho"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 20)
    out_json = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(app, [str(binary), "-o", str(out_json)])
    assert result.exit_code != 0
    assert "format" in (result.stdout + (result.stderr or "")).lower()
