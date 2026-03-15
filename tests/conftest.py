from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_module(module_name: str, relative_path: str) -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    file_path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
