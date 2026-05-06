# Segments

As your hardware designs grow, keeping all state transitions, signal definitions, and timing logic in a single script quickly becomes unmanageable. While Python functions are excellent for organizing code, calling them normally in noRTL would create a new, separate sequence of states for every call. **Segments** solve this by allowing you to reuse state sequences and drastically reduce the total number of states in your design.

## Why use Segments?
In hardware description, every step in your Python code typically maps to a state in the generated finite state machine (FSM). Without segments, reusing logic (like a UART transmitter or a data processing pipeline) would duplicate states, bloating your design and increasing routing congestion. Segments allow noRTL to:

* **Reduce State Count:** Identical calls to a segment re-use the same underlying state sequence, sharing transitions and logic. A limited number of states leads to a reduced ressource demand due to large multiplexers (which is especially critical for FPGAs)
* **Improve Readability:** Break complex logic into modular, reusable functions that mirror standard software practices.
* **Manage Memory Efficiently:** Automatically handle temporary signals and memory zones for intermediate calculations using scratch managers.

## How to use Segments
You define a segment by decorating a Python function or method with `@Segment`. noRTL analyzes the call signature automatically. The first time a specific signature is called, noRTL executes the function body to generate the corresponding states and transitions. Subsequent calls with the same signature simply jump to the start of that segment and return to the next state after completion.

### Standalone Functions
The most common use case is decorating standalone functions that take the `Engine` (or a helper object) as their first argument.

```python
from nortl import Engine, Segment
from nortl.core.protocols import EngineProto
from nortl.core.operations import Renderable

engine = Engine('DataSender')
output = engine.define_output('OUTPUT', width=1)

@Segment
def send_byte(engine: EngineProto, data: Union[Renderable, int]) -> None:
    """Transmit a byte over the OUTPUT signal."""
    for i in range(8):
        engine.set(output, data[i])
        engine.sync()

# Usage in your main logic:
with engine.while_loop(True):
    # First call: generates the states
    send_byte(engine, 0x4A)
    # Second call: re-uses the exact same state sequence
    send_byte(engine, 0x4B)
```

* When `send_byte(engine, 0x4A)` is called for the first time, noRTL executes the Python code to generate a unique sequence of states for this signature. It creates an entry state, 8 intermediate states (one for each bit transmission), and an exit state.
* When `send_byte(engine, 0x4B)` is called subsequently, noRTL recognizes the identical signature. Instead of generating new states, it inserts a transition that jumps directly to the entry state of the existing sequence. Both calls share the exact same underlying hardware logic and state machine path, demonstrating efficient resource reuse.

### Class Methods
You can also attach segments to methods of helper classes. This is ideal for encapsulating complex subsystems while keeping the top-level script clean.

```python
class BitStreamSender:
    def __init__(self, engine: EngineProto):
        self.engine = engine
        self.output = engine.define_output('OUTPUT', width=1)

    @Segment
    def send_data(self, data: Union[Renderable, int]) -> None:
        for i in range(8):
            self.engine.set(self.output, data[i])
            self.engine.sync()

# Usage:
sender = BitStreamSender(engine)
with engine.while_loop(True):
    sender.send_data(0x4A)
```

## Input and Output Slots
By default, noRTL creates a new state sequence for every unique combination of arguments. If you want to reuse a single state sequence regardless of the input values, you can use **Input Slots**.

Input slots tell noRTL to copy the arguments into temporary scratch signals *before* entering the segment. This allows the segment to ignore the actual values during state generation, effectively creating a parameterized function that shares one FSM path for all inputs.

```python
@Segment.with_input_slots(data=8)
def send_byte(engine: EngineProto, data: Union[Renderable, int]) -> None:
    for i in range(8):
        engine.set(output, data[i])
        engine.sync()
```

You can also use **Output Slots** to safely copy return values out of a segment into scratch signals. This prevents read-only conflicts when the segment is called multiple times in different contexts or branches.

```python
@Segment.with_output_slots(8)
def read_data(engine: EngineProto) -> Union[Renderable, int]:
    # ... logic to read data ...
    return result
```

### Dynamic Slot Widths
Slot widths can be configured flexibly to match your design needs:

* **Fixed Width:** `@Segment.with_input_slots(data=8)` uses a constant bit-width.
* **String References:** `@Segment.with_input_slots(data='width')` copies the width from another argument at runtime.
* **Automatic Detection:** `@Segment.with_input_slots(data=True)` infers the width from the first call's `operand_width`.
* **Disabled:** `@Segment.with_input_slots(data=False)` or omitting the slot entirely disables slot creation.

## Input Checks
To ensure hardware safety and catch configuration errors early, you can validate arguments before a segment is instantiated or called using `with_input_checks`. This is particularly useful when combined with input slots, as the actual function body won't be executed for every different input.

```python
def validate_length(length: int) -> bool:
    return 0 < length <= 32

@Segment.with_input_slots(data=8, length=5).with_input_checks(validate_length)
def send_dynamic(engine: EngineProto, data: Union[Renderable, int], length: int) -> None:
    # ... transmission logic ...
```

You can also pass inline lambda validators for quick checks:
```python
@Segment.with_input_slots(data=8).with_input_checks(length=lambda x: x < 32)
def send_dynamic(engine: EngineProto, data: Union[Renderable, int], length: int) -> None:
    # ...
```
