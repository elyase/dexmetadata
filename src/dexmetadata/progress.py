"""
Progress tracking for batch operations.
"""

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# Console for rich output
console = Console()


class ProgressTracker:
    """Tracks progress for batched operations."""

    def __init__(self, total: int, show_progress: bool = True):
        self.total = total
        self.show_progress = show_progress
        self.progress = None
        self.task_id = None

        if show_progress:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold green]Fetching pool metadata..."),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            )
            self.task_id = self.progress.add_task("Fetching", total=total)

    def start(self):
        """Start displaying progress."""
        if self.progress:
            self.progress.start()

    def update(self, advance: int = 1):
        """Update progress bar."""
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, advance=advance)

    def stop(self):
        """Stop displaying progress."""
        if self.progress:
            self.progress.stop()
