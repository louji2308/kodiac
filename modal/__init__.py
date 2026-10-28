"""Modal infrastructure package and local verification shim for Kodiac."""

from __future__ import annotations

import importlib.machinery
import sys
from typing import Any, Dict


def _find_external_modal():
    for p in sys.path:
        if "Kodiac" not in p and p not in ("", "."):
            spec = importlib.machinery.PathFinder.find_spec("modal", [p])
            if spec and spec.origin and "Kodiac" not in spec.origin:
                try:
                    import types

                    loader = spec.loader
                    if loader:
                        mod = types.ModuleType("real_modal")
                        loader.exec_module(mod)
                        if hasattr(mod, "App") and hasattr(mod, "Volume"):
                            return mod
                except Exception:
                    pass
    return None


_real_modal = _find_external_modal()
HAS_MODAL = _real_modal is not None

if HAS_MODAL:
    App = _real_modal.App
    Volume = _real_modal.Volume
    Secret = _real_modal.Secret
    Image = _real_modal.Image
else:

    class _VolumeShim:
        def __init__(self, name: str, create_if_missing: bool = True):
            self.name = name
            self.create_if_missing = create_if_missing

        @classmethod
        def from_name(cls, name: str, create_if_missing: bool = True):
            return cls(name, create_if_missing)

        def __repr__(self) -> str:
            return f"Volume('{self.name}')"

    class _SecretShim:
        def __init__(self, name: str):
            self.name = name

        @classmethod
        def from_name(cls, name: str):
            return cls(name)

        def __repr__(self) -> str:
            return f"Secret('{self.name}')"

    class _ImageShim:
        @classmethod
        def debian_slim(cls, python_version: str = "3.11"):
            return cls()

        def pip_install(self, *packages):
            return self

    class _AppShim:
        def __init__(self, name: str):
            self.name = name
            self.registered_functions: Dict[str, Dict[str, Any]] = {}

        def function(self, **kwargs):
            def decorator(fn):
                fn.__modal_kwargs__ = kwargs
                self.registered_functions[fn.__name__] = kwargs
                return fn

            return decorator

        def local_entrypoint(self):
            def decorator(fn):
                return fn

            return decorator

    App = _AppShim
    Volume = _VolumeShim
    Secret = _SecretShim
    Image = _ImageShim

__all__ = ["App", "Volume", "Secret", "Image", "HAS_MODAL"]
