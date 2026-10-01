"""Load extra tool modules named in KNOWLEDGE_MCP_PLUGINS.

A plugin is any Python module that defines:

    def register(app: MCPServer, settings: Settings) -> None: ...

Plugins load after the core tools. The SDK keeps the first tool registered under a
name, so a plugin cannot replace a core tool by reusing its name (the duplicate is
ignored with a warning). A plugin that fails to import or register is logged and
skipped, so a broken plugin never takes the core tools down with it.

Plugins run with the same permissions as the server. Only load code you trust.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from types import ModuleType

from mcp.server.mcpserver import MCPServer

from knowledge_mcp.config import Settings

log = logging.getLogger(__name__)


def _import(spec: str) -> ModuleType:
    """Import a dotted module name, or a .py file given by path."""
    if spec.endswith(".py") or "/" in spec:
        path = Path(spec).expanduser().resolve()
        module_spec = importlib.util.spec_from_file_location(
            f"knowledge_mcp_plugin_{path.stem}", path
        )
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return module
    return importlib.import_module(spec)


def load_plugins(app: MCPServer, settings: Settings) -> list[str]:
    """Load each plugin in settings.plugins. Returns the specs that loaded."""
    loaded: list[str] = []
    for spec in settings.plugins:
        try:
            register = getattr(_import(spec), "register", None)
            if not callable(register):
                raise TypeError("plugin has no register(app, settings) function")
            register(app, settings)
        except Exception:
            log.exception("Plugin %r failed to load and was skipped", spec)
            continue
        log.info("Loaded plugin %r", spec)
        loaded.append(spec)
    return loaded
