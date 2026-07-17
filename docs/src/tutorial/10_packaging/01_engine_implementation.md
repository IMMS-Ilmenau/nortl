# Implementing the Engine

Now we write the actual hardware description. We'll build a traffic light controller for a four-way intersection. This example is deliberately simple so you can focus on the packaging aspects, but it exercises the key patterns: port definitions, timer-based delays, conditional logic, and subsystem delegation.

This method follows the idea, that the main class inherits from the `Engine` class of the noRTL package.
In this way, many constructs can be written in a nice way but it limits the reuseability since engines cannot be instantiated within other engines (yet). If this is needed, the engine to be instantiated is to be treated like a normal Verilog module.

## The Main Engine Class

The engine class is the heart of your package. It defines the interface (ports) and the behavior (state machine). Following the composition pattern from [03_classes.md](03_classes.md), the engine delegates subsystem logic to separate controller classes rather than implementing everything inline.

```python
# src/traffic_light/engine.py
from nortl import Engine, Timer
from nortl.core.operations import Const
from nortl.core.protocols import Renderable
from nortl.components.timer import Timer

from .controllers import PedestrianController, EmergencyOverride


class TrafficLightEngine(Engine):
    """Top-level traffic light controller engine.

    This engine orchestrates the traffic light states and delegates
    subsystem logic to dedicated controller classes.
    """

    def __init__(self, module_name: str = "traffic_light"):
        super().__init__(module_name)

        # Clock frequency (1 MHz for this example)
        self.fclk = int(1e6)

        # Timer component
        self.timer = Timer(self, 32)

        # Define ports — the interface to the outside world
        self.ped_request = self.define_input("PED_REQUEST", 1)
        self.emergency = self.define_input("EMERGENCY", 1)

        self.north_en = self.define_output("NORTH_EN", 1, 0)
        self.south_en = self.define_output("SOUTH_EN", 1, 0)
        self.east_en = self.define_output("EAST_EN", 1, 0)
        self.west_en = self.define_output("WEST_EN", 1, 0)

        self.status = self.define_output("STATUS", 4, 0)

        # Subsystem controllers — composition over inheritance
        self.ped_controller = PedestrianController(self)
        self.emergency_ctrl = EmergencyOverride(self)

    def build(self, stop_signal: Renderable | None = None) -> None:
        """Build the state machine for the traffic light.

        Arguments:
            stop_signal: If provided, the main loop exits when this signal
                becomes true. This is useful for testing — the testbench
                can assert a stop signal after verifying one cycle.
        """
        condition = Const(False) if stop_signal is None else ~stop_signal
        with self.while_loop(condition):
            # Check for emergency first
            self.emergency_ctrl.handle_emergency()

            # North-South green phase
            self._set_phase("NS_GREEN")
            self.timer.wait_delay(self.fclk * 10)  # 10 seconds
            # Pedestrian controller integrates inline
            self.ped_controller.check_and_cross(self.ped_request)

            # North-South yellow phase
            self._set_phase("NS_YELLOW")
            self.timer.wait_delay(self.fclk * 3)   # 3 seconds

            # East-West green phase
            self._set_phase("EW_GREEN")
            self.timer.wait_delay(self.fclk * 10)  # 10 seconds
            # Pedestrian controller integrates inline
            self.ped_controller.check_and_cross(self.ped_request)

            # East-West yellow phase
            self._set_phase("EW_YELLOW")
            self.timer.wait_delay(self.fclk * 3)   # 3 seconds

    def _set_phase(self, phase: str) -> None:
        """Set the traffic light outputs for a given phase."""
        match phase:
            case "NS_GREEN":
                self.set(self.north_en, 1)
                self.set(self.south_en, 1)
                self.set(self.east_en, 0)
                self.set(self.west_en, 0)
                self.set(self.status, 0b0001)
            case "NS_YELLOW":
                # Both NS and EW go yellow simultaneously (all-red transition)
                self.set(self.north_en, 0)
                self.set(self.south_en, 0)
                self.set(self.east_en, 0)
                self.set(self.west_en, 0)
                self.set(self.status, 0b0010)
            case "EW_GREEN":
                self.set(self.north_en, 0)
                self.set(self.south_en, 0)
                self.set(self.east_en, 1)
                self.set(self.west_en, 1)
                self.set(self.status, 0b0100)
            case "EW_YELLOW":
                # Both NS and EW go yellow simultaneously (all-red transition)
                self.set(self.north_en, 0)
                self.set(self.south_en, 0)
                self.set(self.east_en, 0)
                self.set(self.west_en, 0)
                self.set(self.status, 0b1000)
```

**Why structure it this way?** The `build()` method contains the entire state machine. It's a single entry point that test code and synthesis scripts both call. By keeping port definitions in `__init__` and behavior in `build()`, we separate *what* the hardware interfaces are from *how* it behaves. This separation that makes testing and reuse cleaner.

Many engines operate with a *main loop*. Without this loop, the actual behavior would be executed just once. For testing purposes, carefully consider which logic to place in the main loop. We recommend that each part of the behavior is placed in functions that are called from this loop. This has the advantage, that each function (i.e. state sequence) can be tested separately. The work of integration the state sequence into the final engine will be done by noRTL internally.

## Subsystem Controllers

The controller classes encapsulate specific behaviors. They receive the `Engine` instance and manage their own signals using `define_local()`. This is the composition pattern in action: instead of the engine class doing everything, each controller owns a slice of the design.

There are two ways to integrate controllers into your engine:

1. **Inline integration** — call controller methods directly from `build()`. The controller's logic executes as part of the main state machine flow. This is the recommended approach for most cases.
2. **Signal-based coordination** — the controller defines local signals that the engine reads to make decisions. Useful when a subsystem needs to communicate status back to the engine without tightly coupling their state machines.

```python
# src/traffic_light/controllers.py
from nortl.core.protocols import EngineProto
from nortl.core.constructs import Condition


class PedestrianController:
    """Handles pedestrian crossing logic.

    When PED_REQUEST is asserted during a green phase, this controller
    extends the phase by waiting for the pedestrian to finish crossing.
    """

    def __init__(self, engine: EngineProto):
        self.engine = engine
        self.crossing_active = engine.define_local("PED_CROSSING", 1, 0)

    def check_and_cross(self, ped_request) -> None:
        """If a pedestrian request is active, wait for crossing before returning.

        This method is called from within a green phase in the main loop.
        If no request is pending, it returns immediately (via sync).
        If a request is active, it waits one second for pedestrians to cross.
        """
        with self.engine.condition(ped_request):
            self.engine.set(self.crossing_active, 1)
            self.engine.sync()
            self.engine.timer.wait_delay(int(1e6))  # 1 second crossing
            self.engine.set(self.crossing_active, 0)
            self.engine.sync()
        with self.engine.else_condition():
            pass


class EmergencyOverride:
    """Handles emergency vehicle override.

    When EMERGENCY is asserted, all directions turn red and the
    engine holds that state until the signal deasserts. Afterward,
    normal operation resumes.
    """

    def __init__(self, engine: EngineProto):
        self.engine = engine
        self.all_red = engine.define_local("ALL_RED", 1, 0)

    def handle_emergency(self) -> None:
        """Check for emergency and handle it inline.

        This method is called at the start of each iteration of the main loop.
        If an emergency is active, it keeps all lights red until the signal
        deasserts, then returns control to the caller.
        """
        with self.engine.condition(self.engine.emergency):
            # Emergency phase: all outputs off
            self.engine.set(self.all_red, 1)
            self.engine.sync()
            self.engine.wait_for(~self.engine.emergency)
            self.engine.set(self.all_red, 0)
            self.engine.sync()
        with self.engine.else_condition():
            pass
```

### Integration Patterns

The key principle is that controller methods are **called directly** from `build()`, making their logic part of the main state machine flow. Looking at the engine code above:

- `self.emergency_ctrl.handle_emergency()` is called at the top of each loop iteration, giving emergency handling the highest priority. Using a `Engine.fork()`, it could also run completely in parallel.
- `self.ped_controller.check_and_cross(self.ped_request)` is called within each green phase, extending the phase only when a pedestrian request is active.

This inline integration means controller methods execute as sequential state transitions within the engine. Each call to a controller method adds states and transitions to the engine's state machine, just like any other noRTL construct called from `build()`.

**Why use `EngineProto` instead of `Engine`?** The controller accepts the `EngineProto` protocol rather than the concrete `Engine` class. This makes the controller testable in isolation and more flexible — any object that implements the engine interface will work. It's a small detail that pays off as your design grows.

**Key pattern:** Controller methods should be called *inside* the state machine flow (within `build()`), not just defined as standalone methods. Each call becomes part of the sequential state transitions, which makes the overall behavior predictable and testable.

## Public API (`__init__.py`)

The package's `__init__.py` defines what users see when they import it:

```python
# src/traffic_light/__init__.py
"""Traffic light controller built with noRTL."""

from .engine import TrafficLightEngine

__all__ = ["TrafficLightEngine"]
```

This is intentionally minimal. Users should only need to know about `TrafficLightEngine` — the controllers are implementation details. If you later expose more classes, add them to `__all__` explicitly rather than relying on wildcard imports. This makes the public API clear and stable.

## Wrapping Custom Verilog IP

So far we've only used noRTL's built-in components like `Timer`. But what if you need a custom Verilog module — a specialized counter, a protocol bridge, or hand-optimized logic that noRTL doesn't provide out of the box? You can still use it, and you should wrap it in a Python class so it feels just as natural to use as anything built into noRTL.

The process has three steps: register the Verilog module with noRTL's library, write a Python wrapper class, then use it in your engine. Let's walk through each one.

### Register the Verilog Module

Before noRTL can render or compile your custom Verilog, it needs to know where the file lives and what ports and parameters the module exposes. You register this in `src/traffic_light/verilog_ip/__init__.py`:

```python
# src/traffic_light/verilog_ip/__init__.py
"""Register custom Verilog IP modules with noRTL."""

from pathlib import Path
from nortl.verilog_library import BUILT_IN_LIB
from nortl.verilog_library.module import Module

VERILOG_IP_DIR = Path(__file__).parent

# Map the module name to its source file
BUILT_IN_LIB["my_counter"] = (VERILOG_IP_DIR / "counter.sv").resolve()


def get_custom_modules():
    """Return a list of custom Verilog modules for compilation.

    This function is called by the test wrapper to collect all
    Verilog source files before compilation. Extend it as you add
    more modules.
    """
    modules = []

    counter_file = VERILOG_IP_DIR / "counter.sv"
    if counter_file.exists():
        with open(counter_file, "r") as f:
            counter_hdl = f.read()
        cnt = Module("my_counter", counter_hdl)
        cnt.add_port("CLK_I")
        cnt.add_port("RST_ASYNC_I")
        cnt.add_port("LOAD")
        cnt.add_port("DATA_I")
        cnt.add_port("DATA_O")
        cnt.add_port("DONE")
        cnt.add_parameter("WIDTH", 8)
        modules.append(cnt)

    return modules
```

This does two things: it tells noRTL where to find `counter.sv` when rendering Verilog, and it gives the renderer the port/parameter metadata it needs to generate correct instantiations. The `get_custom_modules()` function is used by your test wrapper during simulation compilation (see [02_testing_and_artifacts.md](02_testing_and_artifacts.md)).

### Write a Python Wrapper Class

Now that noRTL knows about the module, write a Python class that wraps it — just like the built-in `Timer` wraps `nortl_count_down_timer`. Create `src/traffic_light/ip/counter.py`:

```python
# src/traffic_light/ip/counter.py
from typing import Union

from nortl.core.protocols import EngineProto, ParameterProto, Renderable


class Counter:
    """Python wrapper for the my_counter Verilog IP.

    Instantiates the module, connects its ports, and exposes a
    clean API for loading values and reading results.
    """

    def __init__(
        self,
        engine: EngineProto,
        width: Union[int, ParameterProto] = 8,
        instance_name_prefix: str = "I_CNT",
    ) -> None:
        self.engine = engine

        # Auto-increment the instance name so multiple counters
        # don't collide
        counter_idx = 0
        while (
            instance_name := f"{instance_name_prefix}_{counter_idx}"
        ) in engine.module_instances:
            counter_idx += 1

        self.instance_name = instance_name

        # Create the Verilog instance and set its parameter
        self._module = engine.create_module_instance(
            "my_counter", self.instance_name
        )
        engine.override_module_parameter(self.instance_name, "WIDTH", width)

        # Define local signals and wire them to the module ports
        self.load = engine.define_local(f"{self.instance_name}_load", reset_value=0)
        self.data_in = engine.define_local(f"{self.instance_name}_data_in", width=width)
        self.data_out = engine.define_local(f"{self.instance_name}_data_out", width=width)
        self.done = engine.define_local(f"{self.instance_name}_done", reset_value=0)

        engine.connect_module_port(self.instance_name, "LOAD", self.load)
        engine.connect_module_port(self.instance_name, "DATA_I", self.data_in)
        engine.connect_module_port(self.instance_name, "DATA_O", self.data_out)
        engine.connect_module_port(self.instance_name, "DONE", self.done)

    def load_value(self, value: Union[Renderable, int]) -> None:
        """Load a value and pulse the LOAD signal to trigger it."""
        self.engine.set(self.data_in, value)
        self._pulse_load()

    def _pulse_load(self) -> None:
        """Pulse LOAD high for one cycle."""
        self.engine.set(self.load, 1)
        self.engine.sync()
        self.engine.set(self.load, 0)
        self.engine.sync()

    @property
    def value(self) -> Renderable:
        """Read the current output value."""
        return self.data_out
```

A few things worth noting:

- We accept `EngineProto` rather than `Engine`, so the wrapper works with any engine-like object. This makes it testable in isolation.
- Instance names auto-increment, so you can instantiate multiple counters without worrying about name collisions.
- All the low-level port wiring happens in `__init__`. The public API (`load_value`, `value`) is clean and doesn't expose noRTL internals.

### Use It in Your Engine

With the module registered and the wrapper written, using it in your engine is straightforward:

```python
# src/traffic_light/engine.py (excerpt)
from .ip.counter import Counter

class TrafficLightEngine(Engine):
    def __init__(self, module_name: str = "traffic_light"):
        super().__init__(module_name)

        # ... ports ...

        # Custom Verilog IP wrapper
        self.phase_counter = Counter(self, width=4)

    def build(self) -> None:
        with self.while_loop(Const(True)):
            self.phase_counter.load_value(0)
            self._set_phase("NS_GREEN")
            self.timer.wait_delay(self.fclk * 10)

            self.phase_counter.load_value(1)
            self._set_phase("NS_YELLOW")
            self.timer.wait_delay(self.fclk * 3)

            # Read back the counter value for status reporting
            self.set(self.status, self.phase_counter.value)
```

That's it. The wrapper handles all the plumbing — module instantiation, port connections, parameter overrides — and you get a simple Python interface. This is exactly how the built-in `Timer` component works with `nortl_count_down_timer`, and you can follow the same pattern for any custom Verilog IP you add.
You can even use noRTL-based tests to verify our IP together with your glue logic.
