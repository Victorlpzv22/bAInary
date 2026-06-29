"""Exception hierarchy for the bAInary lifting subsystem."""


class BainaryError(Exception):
    """Base for all bAInary-raised errors."""


class LifterError(BainaryError):
    """The lifting backend (e.g. Ghidra subprocess) failed.

    Carries ``stderr`` (captured from the subprocess) and ``returncode``
    for debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class SchemaValidationError(BainaryError):
    """The intermediate JSON did not match the Pydantic schema.

    Carries ``field`` (the schema field that failed) and
    ``function_address`` (the function it belonged to, if known) so the
    caller can pinpoint the issue in a large artifact.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str = "",
        function_address: str = "",
    ) -> None:
        if function_address:
            message = f"{message} (function_address={function_address})"
        super().__init__(message)
        self.field = field
        self.function_address = function_address
