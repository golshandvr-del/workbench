"""Project Workbench shell (roadmap 2.3.0+, ADR-007): one workspace over the existing V2 services.

``controller.WorkspaceController`` provides read models and actions; ``shell.WorkspaceWindow`` is the
Tk presentation. Neither contains domain logic: they delegate to ``ProjectsController`` / ``aiwb.v2``.
"""
