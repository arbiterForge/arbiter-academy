from __future__ import annotations

import errno
import time
from collections.abc import Callable
from typing import Protocol


class CleanableTemporaryDirectory(Protocol):
    def cleanup(self) -> None: ...


def cleanup_temporary_directory(
    temporary: CleanableTemporaryDirectory,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Remove a temporary tree despite a brief Git pack-file teardown race."""
    for attempt in range(5):
        try:
            temporary.cleanup()
            return
        except OSError as error:
            if error.errno != errno.ENOTEMPTY or attempt == 4:
                raise
            sleep(0.05 * (2**attempt))
