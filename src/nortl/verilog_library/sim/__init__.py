"""Simulation library."""

from pathlib import Path
from typing import Mapping

from nortl.core.module import Module

__all__ = [
    'SIM_MODULES',
]


VERILOG_SIM_LIBRARY_DIR = Path(__file__).parent


class LibraryModule(Module):
    def __init__(self, module_name: str):
        self.filepath = VERILOG_SIM_LIBRARY_DIR / (module_name + '.sv')

        if not self.filepath.exists() and self.filepath.is_file():
            raise RuntimeError(f'Could not resolve module {module_name} in built-in Verilog library.')

        super().__init__(module_name, self.filepath.read_text(encoding='utf8'))


def load_sim_modules() -> Mapping[str, LibraryModule]:
    """Get simulation modules."""
    modules = {}

    # Coverage writer
    coverage_writer = LibraryModule('coverage_writer')
    modules['coverage_writer'] = coverage_writer

    # Value capture
    value_capture = LibraryModule('value_capture')
    modules['value_capture'] = value_capture

    # Logger
    logger = LibraryModule('logger')
    modules['logger'] = logger

    return modules


SIM_MODULES = load_sim_modules()
"""Library of simulation modules."""
