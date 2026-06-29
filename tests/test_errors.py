from bainary.lift.errors import (
    BainaryError,
    LifterError,
    SchemaValidationError,
)


def test_bainary_error_is_exception():
    assert issubclass(BainaryError, Exception)


def test_lifter_error_is_bainary_error():
    assert issubclass(LifterError, BainaryError)


def test_schema_validation_error_is_bainary_error():
    assert issubclass(SchemaValidationError, BainaryError)


def test_lifter_error_carries_subprocess_log():
    err = LifterError("ghidra crashed", stderr="some stderr output")
    assert err.stderr == "some stderr output"
    assert "ghidra crashed" in str(err)


def test_schema_validation_error_carries_field_and_address():
    err = SchemaValidationError(
        "missing field",
        field="pseudocode",
        function_address="0x401000",
    )
    assert err.field == "pseudocode"
    assert err.function_address == "0x401000"
    assert "0x401000" in str(err)
