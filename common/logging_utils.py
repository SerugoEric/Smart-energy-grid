"""Shared output helper: write a program's output to the screen AND to a log file.

PURPOSE
    Every program in this project prints measurements that must appear in a
    screenshot, and the same numbers must also survive in a file so they can be
    pasted into the report later without being retyped by hand.

INPUTS
    Any callable that prints. The module supplies run_with_log() to wrap it.

OUTPUTS
    - everything the wrapped function prints, still on the terminal
    - a file under logs/ named <prefix>_<CAT timestamp>.txt

HOW TO RUN
    Imported, not run directly:
        from common.logging_utils import run_with_log

        run_with_log("meters_load", main)
"""

import sys


class Tee:
    """Send every write to two streams at once: the terminal and a file.

    WHY A CLASS INSTEAD OF A PRINT FUNCTION
        Some programs print from deep inside a helper or a loop. Replacing
        sys.stdout means those prints are captured too, with no need to pass a
        logger through every function signature.

    WHY THIS IS SAFE
        write() returns the number of characters it handled, which is what
        print() expects back. Returning anything else can raise "unknown error"
        from inside print. flush() is forwarded to both streams so output appears
        immediately, which matters when a program is being watched live.
    """

    def __init__(self, file_handle, original_stream):
        self.file_handle = file_handle
        self.original_stream = original_stream

    def write(self, text: str) -> int:
        self.original_stream.write(text)
        self.file_handle.write(text)
        return len(text)

    def flush(self) -> None:
        self.original_stream.flush()
        self.file_handle.flush()


def run_with_log(prefix: str, function, suffix: str = ".txt") -> None:
    """Run function(), teeing everything it prints to logs/<prefix>_<stamp><suffix>.

    Parameters
        prefix    a short label such as "meters_load"
        function  the callable to run, taking no arguments
        suffix    log file extension, default .txt

    The previous stdout is always restored, even if the function raises, so one
    failed run cannot leave stdout redirected for the next program in the same
    session.
    """
    from common.db import timestamped_log_path

    log_path = timestamped_log_path(prefix, suffix)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w", encoding="utf-8") as log_handle:
        original_stdout = sys.stdout
        sys.stdout = Tee(log_handle, original_stdout)
        try:
            function()
        finally:
            sys.stdout = original_stdout

    print(f"Output also saved to {log_path}")