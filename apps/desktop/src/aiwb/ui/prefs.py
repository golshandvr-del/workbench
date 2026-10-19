"""Application-wide view preferences (roadmap 3.0.0, ADR-009).

Theme, language and Simple/Advanced mode belong to the *application*, not to a
window or a project: one value, stored in the app ``settings.json``
(``ui_theme`` / ``ui_lang`` / ``ui_mode``), observed by every page. Changing a
preference never writes project state.
"""
from __future__ import annotations

from typing import Any, Callable

THEMES = ("light", "dark")
LANGS = ("en", "fa")
MODES = ("simple", "advanced")
DEFAULTS = {"theme": "light", "lang": "en", "mode": "simple"}


class AppPrefs:
    def __init__(self, data: dict[str, Any] | None = None, *, save: Callable[[dict[str, Any]], None] | None = None) -> None:
        data = data or {}
        self.theme = data.get("ui_theme") if data.get("ui_theme") in THEMES else DEFAULTS["theme"]
        self.lang = data.get("ui_lang") if data.get("ui_lang") in LANGS else DEFAULTS["lang"]
        self.mode = data.get("ui_mode") if data.get("ui_mode") in MODES else DEFAULTS["mode"]
        self._save = save
        self._listeners: list[Callable[[str], None]] = []

    # -- observation
    def subscribe(self, fn: Callable[[str], None]) -> Callable[[], None]:
        self._listeners.append(fn)

        def unsubscribe() -> None:
            if fn in self._listeners:
                self._listeners.remove(fn)
        return unsubscribe

    def _changed(self, key: str) -> None:
        if self._save is not None:
            self._save(self.as_settings())
        for fn in list(self._listeners):
            fn(key)

    # -- values
    def as_settings(self) -> dict[str, str]:
        return {"ui_theme": self.theme, "ui_lang": self.lang, "ui_mode": self.mode}

    @property
    def rtl(self) -> bool:
        return self.lang == "fa"

    @property
    def advanced(self) -> bool:
        return self.mode == "advanced"

    def tr(self, pair: tuple[str, str]) -> str:
        return pair[1] if self.lang == "fa" else pair[0]

    def set_theme(self, theme: str) -> None:
        if theme not in THEMES:
            raise ValueError("theme must be light or dark")
        if theme != self.theme:
            self.theme = theme
            self._changed("theme")

    def set_lang(self, lang: str) -> None:
        if lang not in LANGS:
            raise ValueError("language must be en or fa")
        if lang != self.lang:
            self.lang = lang
            self._changed("lang")

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError("mode must be simple or advanced")
        if mode != self.mode:
            self.mode = mode
            self._changed("mode")
