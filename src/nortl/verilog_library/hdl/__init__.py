"""Design Library."""

from pathlib import Path
from typing import Mapping

from nortl.core.module import Module

__all__ = [
    'HDL_MODULES',
]


VERILOG_HDL_LIBRARY_DIR = Path(__file__).parent


class LibraryModule(Module):
    def __init__(self, module_name: str):
        self.filepath = VERILOG_HDL_LIBRARY_DIR / (module_name + '.sv')

        if not self.filepath.exists() and self.filepath.is_file():
            raise RuntimeError(f'Could not resolve module {module_name} in built-in Verilog library.')

        super().__init__(module_name, self.filepath.read_text(encoding='utf8'))


def load_hdl_modules() -> Mapping[str, LibraryModule]:
    """Get HDL modules."""
    modules = {}

    sync = LibraryModule('nortl_sync')
    sync.add_port('IN')
    sync.add_port('OUT')
    sync.add_parameter('DATA_WIDTH', 1)
    sync.add_port('CLK_REQ')
    sync.set_clk_request('CLK_REQ')
    modules['nortl_sync'] = sync

    edge_detect = LibraryModule('nortl_edge_detector')
    edge_detect.add_port('SIGNAL')
    edge_detect.add_port('RISING')
    edge_detect.add_port('FALLING')
    edge_detect.add_port('CLK_REQ')
    edge_detect.set_clk_request('CLK_REQ')
    modules['nortl_edge_detector'] = edge_detect

    delay = LibraryModule('nortl_delay')
    delay.add_port('IN')
    delay.add_port('OUT')
    delay.add_parameter('DATA_WIDTH', 1)
    delay.add_parameter('DELAY_STEPS', 1)
    delay.add_port('CLK_REQ')
    delay.set_clk_request('CLK_REQ')
    modules['nortl_delay'] = delay

    timer = LibraryModule('nortl_count_down_timer')
    timer.add_port('RELOAD')
    timer.add_port('ZERO')
    timer.add_port('DELAY')
    timer.add_parameter('DATA_WIDTH', 1)
    timer.add_port('CLK_REQ')
    timer.set_clk_request('CLK_REQ')
    modules['nortl_count_down_timer'] = timer

    # Ports are not defined here -- should not be used directly!
    modules['nortl_clock_gate'] = LibraryModule('nortl_clock_gate')

    return modules


HDL_MODULES = load_hdl_modules()
"""Library of HDL modules."""
