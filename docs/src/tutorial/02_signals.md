
# Signals and Variables

Understanding how signals work in noRTL is crucial for writing correct hardware descriptions. Unlike software, hardware signals change state on clock edges, and noRTL abstracts this timing away while ensuring deterministic behavior.

## Python Assignment vs. `engine.set()`
In standard Python, assigning a variable (`x = 5`) happens instantly and overwrites the previous value. In hardware description, signals are driven by clock cycles and state transitions. noRTL handles this with the `engine.set()` method.

When you call `engine.set(signal, value)`, you are **not** writing to the signal immediately. Instead, you are scheduling an assignment that will be applied on the next clock cycle (or when the state machine transitions). This allows you to write sequential-looking code while noRTL correctly maps the assignments to the appropriate clock edge. You can set multiple signals in one state, and they will all update simultaneously on the next cycle. If you need to force an update immediately, you can use `engine.sync()` to advance the state machine.

## Types of Signals
noRTL provides four distinct signal types, each mapped to specific Verilog constructs and managed by the `SignalManager`:

* `input`: External signals entering your module. These are read-only and cannot be assigned by your logic. Created via `engine.define_input(name, width)`.
* `output`: Ports driven by your design. They can be implemented as registers (with an optional `reset_value`) or as continuous combinational assignments. Created via `engine.define_output(name, width, reset_value=0)`.
* `local`: Internal signals that act as wires or registers within your module but are not exposed as ports. Local signals support special behaviors like `pulsing` (automatically resets to `0` if not set in the current state) and can also be used for combinational assignments. Created via `engine.define_local(name, width)`.
* `scratch`: Temporary signals managed by the internal `ScratchManager`. They do not map to individual Verilog registers but share a dynamically allocated scratch pad. They are ideal for intermediate calculations and temporary storage. Created via `engine.define_scratch(width)`.

## Behavior of Scratch Signals
Scratch signals are designed to simplify complex control logic by providing temporary storage without manually crafting state machines for every intermediate value. They are managed automatically by noRTL's internal memory manager.

### Use-Cases
Use scratch signals when you need temporary storage that shouldn't pollute your global signal namespace or require explicit reset logic. Common examples include:
* Returning data from functions.
* Holding intermediate results during multi-step arithmetic or logic operations.
* Acting as temporary counters or indices for loops and array accesses.
* Storing flags or control bits that only need to exist within a specific branch of your state machine.


### Creation
Create a scratch signal using `engine.define_scratch(width)`. This returns a `ScratchSignal` object that you can use directly in assignments and conditions. Under the hood, noRTL's `ScratchManager` maps these signals to a shared scratch pad (a local internal signal) within the current memory zone. You don't need to worry about Verilog register declarations or bit-width matching; the manager handles the hardware allocation automatically by finding free bit ranges in the shared pad using a dynamic allocation algorithm.

### Scoping & Lifecycle
Scratch signals follow a strict scoping and lifecycle model. This ensures resources are never leaked and prevents naming collisions.

* **Automatic Allocation:** When you enter a new control context (like a loop or a conditional block), noRTL automatically activates a new memory zone. Any scratch signals created within this zone are allocated in the active scratch pad.
* **Automatic Release:** When the context exits, the zone is deactivated, and all scratch signals allocated within it are automatically released. Their bit positions in the scratch pad become available for reuse.
* **Safe Reuse:** Because signals are tied to their zone's lifecycle, you can safely create scratch signals with the same name or width in different branches of your code. noRTL ensures they don't interfere with each other by managing their lifetimes independently.
