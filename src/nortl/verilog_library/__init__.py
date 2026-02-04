from pathlib import Path
from typing import List

from nortl.core.module import Module

VERILOG_LIBRARY_DIR = Path(__file__).parent

BUILT_IN_LIB = {
    'nortl_sync': (VERILOG_LIBRARY_DIR / 'nortl_sync.sv').resolve(),
    'nortl_edge_detector': (VERILOG_LIBRARY_DIR / 'nortl_edge_detector.sv').resolve(),
    'nortl_delay': (VERILOG_LIBRARY_DIR / 'nortl_delay.sv').resolve(),
    'nortl_count_down_timer': (VERILOG_LIBRARY_DIR / 'nortl_count_down_timer.sv').resolve(),
    'nortl_clock_gate': (VERILOG_LIBRARY_DIR / 'nortl_clock_gate.sv').resolve(),
}


def get_modules() -> List[Module]:
    module_list = []

    hdl_sync = ''
    with open(BUILT_IN_LIB['nortl_sync'], 'r') as file:
        hdl_sync = file.read()

    sync = Module('nortl_sync', hdl_sync)
    sync.add_port('IN')
    sync.add_port('OUT')
    sync.add_parameter('DATA_WIDTH', 1)
    sync.add_port('CLK_REQ')
    sync.set_clk_request('CLK_REQ')
    module_list.append(sync)

    hdl_edge_detect = ''
    with open(BUILT_IN_LIB['nortl_edge_detector'], 'r') as file:
        hdl_edge_detect = file.read()

    edge_detect = Module('nortl_edge_detector', hdl_edge_detect)
    edge_detect.add_port('SIGNAL')
    edge_detect.add_port('RISING')
    edge_detect.add_port('FALLING')
    edge_detect.add_port('CLK_REQ')
    edge_detect.set_clk_request('CLK_REQ')
    module_list.append(edge_detect)

    hdl_delay = ''
    with open(BUILT_IN_LIB['nortl_delay'], 'r') as file:
        hdl_delay = file.read()

    delay = Module('nortl_delay', hdl_delay)
    delay.add_port('IN')
    delay.add_port('OUT')
    delay.add_parameter('DATA_WIDTH', 1)
    delay.add_parameter('DELAY_STEPS', 1)
    delay.add_port('CLK_REQ')
    delay.set_clk_request('CLK_REQ')
    module_list.append(delay)

    hdl_timer = ''
    with open(BUILT_IN_LIB['nortl_count_down_timer'], 'r') as file:
        hdl_timer = file.read()

    timer = Module('nortl_count_down_timer', hdl_timer)
    timer.add_port('RELOAD')
    timer.add_port('ZERO')
    timer.add_port('DELAY')
    timer.add_parameter('DATA_WIDTH', 1)
    module_list.append(timer)

    cg = ''
    with open(BUILT_IN_LIB['nortl_clock_gate'], 'r') as file:
        cg = file.read()
    # Ports are not defined here -- should not be used directly!
    module_list.append(Module('nortl_clock_gate', cg))

    return module_list
