# Integrating Verilog Modules (Example: Block RAM)

While noRTL provides powerful high-level constructs for sequential design, you will often need to integrate existing or third-party IP cores. noRTL makes this process seamless by allowing you to wrap any Verilog module in a Python class and connect it to your engine's logic. Let's walk through this using a Block RAM as an example.

## Providing a Verilog Module

First, we need our target hardware description. Here is a simple synchronous Block RAM with a pipeline register for reads and clock-gating support:

```systemverilog
// hdl/generated/nortl/nortl_block_ram.sv
module nortl_block_ram #(
    parameter ADDR_WIDTH = 8,
    parameter DATA_WIDTH = 32,
    parameter RAM_DEPTH = 1 << ADDR_WIDTH
) (
    input  logic              CLK_I, // Clock and reset names are defined by convention. Leave unconnected if you dont need them
    input  logic              RST_ASYNC_I,
    input  logic              WR_EN,
    input  logic [ADDR_WIDTH-1:0] ADDR_I,
    input  logic [DATA_WIDTH-1:0] WR_DATA_I,
    output logic [DATA_WIDTH-1:0] RD_DATA_O,
    output logic              CLK_REQ
);
    logic [DATA_WIDTH-1:0] ram [0:RAM_DEPTH-1];

    // Kept high so the RAM stays clocked when the renderer enables clock gating.
    assign CLK_REQ = 1'b1;

    // Synchronous write
    always_ff @(posedge CLK_I or posedge RST_ASYNC_I) begin
        if (RST_ASYNC_I) begin
            // Optional: initialize RAM contents
        end else if (WR_EN) begin
            ram[ADDR_I] <= WR_DATA_I;
        end
    end

    // Synchronous read with pipeline register
    always_ff @(posedge CLK_I or posedge RST_ASYNC_I) begin
        if (RST_ASYNC_I) begin
            RD_DATA_O <= 0;
        end else begin
            RD_DATA_O <= ram[ADDR_I];
        end
    end

endmodule
```

## Registering a Module for the Engine

By default, noRTL can only instantiate the built-in modules in `nortl.verilog_library.HDL_MODULES`. Custom modules must be registered using the `add_module()` method, before attempting to create an instance using `create_module_instance()`.

Providing the source code for the module will allow the noRTL test wrapper to use the module during simulation.
The example below registers a block RAM. The code is wrapped in a registration function for re-usability.

```python
from pathlib import Path

from nortl.core.module import Module
from nortl.core.protocols import EngineProto

def register_block_ram(engine: EngineProto, hdl_path: Path) -> None:
    """Register block RAM module on engine."""
    ram = Module('nortl_block_ram', hdl_path.read_text())
    ram.add_port('WR_EN')
    ram.add_port('ADDR_I')
    ram.add_port('WR_DATA_I')
    ram.add_port('RD_DATA_O')
    ram.add_parameter('ADDR_WIDTH', 8)
    ram.add_parameter('DATA_WIDTH', 32)

    # The renderer connects CLK_REQ only when to_verilog(clock_gating=True).
    ram.add_port('CLK_REQ')
    ram.set_clk_request('CLK_REQ')
    engine.add_module(ram)
```

## Wrapping the Module in a Python Class

We create a Python class that handles instantiation, parameter overriding, and port mapping. This class acts as a bridge between your sequential Python code and the synthesized Verilog logic.

```python
from typing import Union, List

from nortl.core.protocols import EngineProto, Renderable

class BlockRam:
    def __init__(
        self,
        engine: EngineProto,
        addr_width: int = 8,
        data_width: int = 32,
        instance_name_prefix: str = 'I_RAM'
    ) -> None:
        self.engine = engine
        self.data_width = data_width

        # The following block prevents name collisions
        ram_idx = 0
        while (instance_name := f'{instance_name_prefix}_{ram_idx}') in engine.module_instances:
            ram_idx += 1
        self.instance_name = instance_name

        # register_block_ram(engine, ...) must have run first.
        self.ram_module = self.engine.create_module_instance('nortl_block_ram', self.instance_name)
        self.engine.override_module_parameter(self.instance_name, 'ADDR_WIDTH', addr_width)
        self.engine.override_module_parameter(self.instance_name, 'DATA_WIDTH', data_width)

        # Inputs of the IP are locals with a reset value. The read-data
        # output is a local without a reset value, so the FSM does not drive it.
        self.wr_en = self.engine.define_local(f'{self.instance_name}_wr_en', reset_value=0)
        self.addr = self.engine.define_local(f'{self.instance_name}_addr', width=addr_width, reset_value=0)
        self.wr_data = self.engine.define_local(f'{self.instance_name}_wr_data', width=data_width, reset_value=0)
        self.rd_data = self.engine.define_local(f'{self.instance_name}_rd_data', width=data_width)

        # Connect Python signals to Verilog ports
        self.engine.connect_module_port(self.instance_name, 'WR_EN', self.wr_en)
        self.engine.connect_module_port(self.instance_name, 'ADDR_I', self.addr)
        self.engine.connect_module_port(self.instance_name, 'WR_DATA_I', self.wr_data)
        self.engine.connect_module_port(self.instance_name, 'RD_DATA_O', self.rd_data)
```

For connecting input ports of the Verilog module, it is recommended to use local signals with a reset value to ensure they are defined at startup. Output signals of the IP are local signals *without* reset value and will therefore be treated like wires in Verilog.

## Gluing Logic: Read and Write Operations

Now that our hardware is wrapped, we can control it using noRTL's sequential constructs. The `engine.set()` and `engine.sync()` methods allow us to schedule operations across clock cycles.

## Single Operation (Scratch Variable)

For standard use cases, a `read` operation will schedule an address, wait for one clock cycle, and return a signal object. This signal acts as a "scratch variable" that you can directly use in subsequent logic, comparisons, or assignments.

```python
    def write(self, addr: Renderable, data: Renderable) -> None:
        """Perform a synchronous write operation."""
        self.engine.set(self.addr, addr)
        self.engine.set(self.wr_data, data)
        self.engine.set(self.wr_en, 1)
        self.engine.sync()
        self.engine.set(self.wr_en, 0)
        self.engine.sync()

    def read(self, addr: Renderable) -> Renderable:
        """Perform a synchronous read operation. Returns a scratch signal representing the read data."""
        ret = self.engine.define_scratch(self.data_width)
        self.engine.set(self.addr, addr)
        self.engine.set(self.wr_en, 0)
        self.engine.sync()
        # rd_data is now valid on the next cycle
        self.engine.set(ret, self.rd_data)
        self.engine.sync()
        return ret
```

## Batch Operations

Sometimes you need to transfer multiple values efficiently without breaking your sequential flow. noRTL's context managers and `sync()` calls make it easy to implement burst interfaces that accept lists of addresses or data.

```python
    def burst_write(self, addresses: List[Renderable], data: List[Renderable]) -> None:
        """Write a list of values to consecutive or specified addresses."""
        for addr, val in zip(addresses, data):
            self.write(addr, val)

    def burst_read(self, addresses: List[Renderable]) -> List[Renderable]:
        """Read a list of values from specified addresses. Returns a list of signal objects."""
        results = []
        for addr in addresses:
            results.append(self.read(addr))
        return results
```

With this wrapper in place, you can now register the module using `register_block_ram()`, instantiate `BlockRam` in your engine, feed it addresses and data using `engine.set()`, and chain read/write operations alongside your other noRTL constructs. The resulting Verilog will automatically include your custom RAM module, correctly instantiated and connected to your control logic!
