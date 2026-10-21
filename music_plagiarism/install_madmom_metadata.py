"""Complete the missing models-package metadata in madmom's GitHub ZIP.

Only the upstream initializer/license are copied; pretrained madmom weights
are not installed or used. The DBN processors consume Beat Transformer outputs.
"""
import argparse
import importlib.metadata
from pathlib import Path
import shutil
import sys


def install(allow_system=False):
    if sys.prefix == sys.base_prefix and not allow_system:
        raise ValueError("Run with the standalone .venv interpreter; Docker uses --allow-system")
    distribution = importlib.metadata.distribution("madmom")
    target = Path(distribution.locate_file("madmom/models"))
    if (target / "__init__.py").is_file():
        print("madmom models metadata already installed")
        return
    source = Path(__file__).resolve().parent / "vendor/madmom_models"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "LICENSE"):
        shutil.copyfile(source / name, target / name)
    print("Installed pinned madmom model metadata (no pretrained weights)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-system", action="store_true")
    install(parser.parse_args().allow_system)
