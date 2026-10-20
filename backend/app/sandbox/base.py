from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    memory_kb: int
    timed_out: bool = False
    compilation_error: bool = False


class SandboxUnavailableError(RuntimeError):
    """Raised when the configured sandbox cannot service an execution request."""


class SandboxRunner(ABC):
    @abstractmethod
    async def execute(
        self,
        language: str,
        source_code: str,
        stdin_data: str,
        time_limit_ms: int = 2000,
        memory_limit_kb: int = 262144,
    ) -> ExecutionResult:
        """Executes code in an isolated environment with resource bounds."""
        pass