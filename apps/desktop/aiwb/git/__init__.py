"""Git integration services for AI Workbench.

The package has no Tkinter dependency. UI code should call these services through
small adapters and must not construct Git subprocess calls itself.
"""
from .models import GitStatusEntry, GitStatusSnapshot
from .service import GitCommandError, GitCommandRunner, GitService

__all__ = [
    "GitCommandError",
    "GitCommandRunner",
    "GitService",
    "GitStatusEntry",
    "GitStatusSnapshot",
]
