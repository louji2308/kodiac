"""Modal Hello CPU smoke test and configuration validator.

Validates CPU container execution and standard volumes/secrets attachments
with strict scaledown_window=0 enforcement.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

try:
    from modal import App, Image
except ImportError:
    try:
        from __init__ import App, Image  # type: ignore
    except ImportError:
        class Image:  # type: ignore
            @classmethod
            def debian_slim(cls, python_version: str = "3.11"):
                return cls()

            def pip_install(self, *packages):
                return self

        class App:  # type: ignore
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

# Import volume and secret definitions
try:
    from modal.volumes import SECRETS, VOLUMES
    from modal.volumes import check as check_volumes
except ImportError:
    from volumes import SECRETS, VOLUMES  # type: ignore
    from volumes import check as check_volumes


# Cost guard constant
SCALEDOWN_WINDOW = 0

app = App("kodiac-hello-cpu")
image = Image.debian_slim(python_version="3.11").pip_install("pydantic>=2.0")


@app.function(
    image=image,
    volumes=VOLUMES,
    secrets=SECRETS,
    scaledown_window=SCALEDOWN_WINDOW,
    timeout=60,
)
def hello_cpu() -> Dict[str, Any]:
    """Execute simple CPU health probe."""
    import platform

    return {
        "status": "ok",
        "compute": "cpu",
        "python": platform.python_version(),
        "scaledown_window": SCALEDOWN_WINDOW,
        "message": "Kodiac CPU container healthy",
    }


@app.local_entrypoint()
def main():
    print("Executing hello_cpu remotely on Modal...")
    result = hello_cpu.remote()
    print("Result:", result)


def check() -> bool:
    """Verify structural validity and cost guards without requiring live Modal connection."""
    check_volumes()
    assert app.name == "kodiac-hello-cpu", f"Unexpected app name: {app.name}"
    if hasattr(app, "registered_functions"):
        assert "hello_cpu" in app.registered_functions
        kwargs = app.registered_functions["hello_cpu"]
        assert kwargs.get("scaledown_window") == 0, "Cost guard violation: scaledown_window != 0"

    # Verify function attributes directly
    if hasattr(hello_cpu, "__modal_kwargs__"):
        assert hello_cpu.__modal_kwargs__.get("scaledown_window") == 0, (
            "scaledown_window must be exactly 0"
        )
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        if check():
            print(
                f"[CHECK PASS] modal/hello_cpu.py: scaledown_window={SCALEDOWN_WINDOW} verified."
            )
            sys.exit(0)
        else:
            sys.exit(1)
    main()
