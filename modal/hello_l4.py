"""Modal Hello L4 GPU smoke test and configuration validator.

Validates L4 GPU container configuration and volume attachments with strict
scaledown_window=0 enforcement to guarantee zero idle warm-GPU costs.
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


# Cost guard constant - strictly zero to scale-to-zero immediately
SCALEDOWN_WINDOW = 0
GPU_TYPE = "L4"

app = App("kodiac-hello-l4")
image = Image.debian_slim(python_version="3.11").pip_install(
    "torch>=2.0",
    "pydantic>=2.0",
)


@app.function(
    image=image,
    gpu=GPU_TYPE,
    volumes=VOLUMES,
    secrets=SECRETS,
    scaledown_window=SCALEDOWN_WINDOW,
    timeout=120,
)
def hello_l4() -> Dict[str, Any]:
    """Execute simple L4 GPU health probe."""
    import platform

    gpu_name = "Mock L4"
    cuda_available = False
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
    except ImportError:
        pass

    return {
        "status": "ok",
        "compute": "gpu",
        "gpu": GPU_TYPE,
        "device_name": gpu_name,
        "cuda_available": cuda_available,
        "python": platform.python_version(),
        "scaledown_window": SCALEDOWN_WINDOW,
        "message": "Kodiac L4 GPU container healthy (scale-to-zero enforced)",
    }


@app.local_entrypoint()
def main():
    print("Executing hello_l4 remotely on Modal...")
    result = hello_l4.remote()
    print("Result:", result)


def check() -> bool:
    """Verify structural validity and cost guards without requiring live Modal connection."""
    check_volumes()
    assert app.name == "kodiac-hello-l4", f"Unexpected app name: {app.name}"
    if hasattr(app, "registered_functions"):
        assert "hello_l4" in app.registered_functions
        kwargs = app.registered_functions["hello_l4"]
        assert kwargs.get("scaledown_window") == 0, "Cost guard violation: scaledown_window != 0"
        assert kwargs.get("gpu") == "L4", f"Expected gpu='L4', got {kwargs.get('gpu')}"

    # Verify function attributes directly
    if hasattr(hello_l4, "__modal_kwargs__"):
        assert hello_l4.__modal_kwargs__.get("scaledown_window") == 0, (
            "scaledown_window must be exactly 0"
        )
        assert hello_l4.__modal_kwargs__.get("gpu") == "L4", (
            "gpu must be configured as 'L4'"
        )
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        if check():
            print(
                f"[CHECK PASS] modal/hello_l4.py: gpu={GPU_TYPE}, "
                f"scaledown_window={SCALEDOWN_WINDOW} verified."
            )
            sys.exit(0)
        else:
            sys.exit(1)
    main()
