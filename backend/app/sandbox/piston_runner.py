import httpx
from app.config import settings
from app.sandbox.base import ExecutionResult, SandboxRunner, SandboxUnavailableError

class PistonRunner(SandboxRunner):
    def __init__(self, endpoint_url:str = settings.PISTON_URL):
        self.endpoint_url = endpoint_url

    async def execute(
        self,
        language: str,
        source_code: str,
        stdin_data: str,
        time_limit_ms: int = 2000,
        memory_limit_kb: int = 262144,
    ):
        # Normalizing language aliases for piston
        lang_map = {
            "python": "python",
            "cpp": "c++",
            "java": "java",
            "javascript": "javascript",
        }

        target_lang = lang_map.get(language.lower(), language.lower())

        payload = {
            "language": target_lang,
            "version": "*",
            "files": [
                {
                    "name": "solution.py" if target_lang == "python" else "Solution",
                    "content": source_code,
                }
            ],
            "stdin": stdin_data,
            "run_timeout": max(1, time_limit_ms),
            "memory_limit": memory_limit_kb * 1024,
            "compile_timeout": 5000,
        }

        timeout_sec = (max(1, time_limit_ms) / 1000.0) + 8.0

        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            try:
                resp = await client.post(self.endpoint_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            except httpx.TimeoutException:
                return ExecutionResult(
                    stdout="",
                    stderr="Execution timed out",
                    exit_code=1,
                    runtime_ms=time_limit_ms,
                    memory_kb=0,
                    timed_out=True,
                )
            except httpx.HTTPError as exc:
                raise SandboxUnavailableError("Piston execution service is unavailable") from exc

        # Check the compilation stage 
        compile_data = data.get("compile")
        if compile_data and compile_data.get("code", 0) != 0:
            return ExecutionResult(
                stdout="",
                stderr=compile_data.get("stderr", "Compilation Error"),
                exit_code=compile_data.get("code", 1),
                runtime_ms=0,
                memory_kb=0,
                timed_out=False,
                compilation_error=True,
            )

        run_data = data.get("run", {})
        stdout = run_data.get("stdout", "")
        stderr = run_data.get("stderr", "")
        code = run_data.get("code", 0)
        signal = run_data.get("signal")

        timed_out = signal in {"SIGKILL", "SIGXCPU"}
        runtime_seconds = run_data.get("time")
        runtime_ms = (
            int(float(runtime_seconds) * 1000)
            if runtime_seconds is not None
            else 0
        )
        memory_bytes = run_data.get("memory", 0) or 0

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=code if code is not None else -1,
            runtime_ms=runtime_ms,
            memory_kb=int(memory_bytes / 1024),
            timed_out=timed_out,
        )
