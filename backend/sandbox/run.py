"""
Sandbox Execution Harness

Runs inside the anylegal-sandbox Docker container.
Reads Python code from /sandbox/code.py, executes it with stdout/stderr capture,
scans /sandbox/output/ for produced files, and writes a JSON result summary.
"""

import contextlib
import io
import json
import os
import signal
import sys
import traceback

CODE_PATH = "/sandbox/code.py"
OUTPUT_DIR = "/sandbox/output"
RESULT_PATH = os.path.join(OUTPUT_DIR, "_result.json")
INTERNAL_TIMEOUT = 115  # seconds (5s buffer before Docker kills at 120s)


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError(f"Execution timed out after {INTERNAL_TIMEOUT}s")


def _scan_output_files():
    """Scan /sandbox/output/ for files created by the script (excluding _result.json)."""
    files = []
    for name in os.listdir(OUTPUT_DIR):
        if name == "_result.json":
            continue
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.isfile(path):
            files.append({"name": name, "size": os.path.getsize(path)})
    return files


def _write_result(stdout: str, stderr: str, exit_code: int):
    """Write execution result as JSON."""
    result = {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "files": _scan_output_files(),
    }
    with open(RESULT_PATH, "w") as f:
        json.dump(result, f)


def main():
    # Read code
    if not os.path.exists(CODE_PATH):
        _write_result("", "No code file found at /sandbox/code.py", 1)
        sys.exit(1)

    with open(CODE_PATH, "r") as f:
        code = f.read()

    if not code.strip():
        _write_result("", "Empty code file", 1)
        sys.exit(1)

    # Set up timeout (Unix only — signal.alarm not available on Windows,
    # but this harness only runs inside the Linux Docker container)
    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(INTERNAL_TIMEOUT)
    except AttributeError:
        pass  # Windows fallback: rely on Docker timeout

    # Capture stdout/stderr
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    exit_code = 0
    try:
        # Execute in a namespace with common imports pre-available
        namespace = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
        }

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(compile(code, CODE_PATH, "exec"), namespace)

    except TimeoutError as e:
        stderr_buf.write(f"\n{e}\n")
        exit_code = 124  # standard timeout exit code

    except SystemExit as e:
        # Allow sys.exit() from user code
        exit_code = e.code if isinstance(e.code, int) else 1

    except Exception:
        stderr_buf.write(traceback.format_exc())
        exit_code = 1

    finally:
        # Cancel timeout
        try:
            signal.alarm(0)
        except AttributeError:
            pass

    # Truncate output to prevent memory issues
    stdout = stdout_buf.getvalue()[:50000]
    stderr = stderr_buf.getvalue()[:20000]

    _write_result(stdout, stderr, exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
