# Data Model

The key to understanding noRTL lies in recognizing how its data structures are designed to enable seamless translation from high-level state machine descriptions to hardware description language (HDL) code. This section elaborates on the architectural decisions behind the data model.

## Representation of a Engine

A noRTL engine consists of a set of states and a set of IOs. Each state has a list of assigns and a list of transitions. This is rather conventional. The new idea of this tool is that these lists can be modified *on the fly*, i.e. during the runtime of the python code.

![Engine as a set of states with a list of assignments and transitions](assets/Engine_Model.svg)

The Python code can be seen as a sort of generator language: The code itself is used to assemble the internal data structure of the engine. The engine object itself provides functions like `engine.sync()` or `engine.jump_if()` that create a new state and a (possibly conditional) transition to this state. The python code is itself assumed to run single-threaded while the generated engine may exhibit parallel behavior. This simplifies the handling of parallel running sub-engines in the final code.

After this data structure has been assembled, it can be converted (i.e. rendered) into Verilog code or other representations.

In this way, an *a priory* declaration can be omitted. Also, signals can be defined at any position in the code. The explanations below are therefore given for reference. Ideally, a user will not be bothered with these details.

### The Single Source of Truth Principle

The entire data model embodies the **single source of truth** principle. Every aspect of the state machine (states, transitions, assignments, signal definitions) is defined once in the `CoreEngine` structure and then used to generate all outputs. This eliminates the risk of having to manually update multiple files when a state machine design changes — a common problem in traditional RTL development.

For example, when adding a new state:

* The state is added to `engine.states`
* Transitions to/from the new state are defined
* Assignments for the new state are configured

Following, the renderers (e.g. VerilogRenderer) may produce the final result from this base.

This approach dramatically reduces cognitive load on the designer and minimizes errors that typically occur when manually updating multiple code locations for a single state machine change.

### CoreEngine: The Central Orchestrator

The `CoreEngine` object serves as the central container for the entire state machine, but its role extends far beyond simple storage. It is designed as a **code generation blueprint** that coordinates all components for output to HDL. This design choice embodies the critical principle of **single source of truth** for the state machine description.

#### State Management and Control Flow

The main idea of the state management is, that the user *never* has to declare states manually. This is done under the hood of the `engine` class.

#### Use Model
In the user's code, the only functions used for state management are:

  - `engine.sync()`: Create a next state and (unconditionally) transition to it.
  - `engine.wait_for(some_condition)`: Create a next state and add a conditional transition. The engine will pause here until the transition can be taken.

For conditional execution, the `engine.jump_if(some_condition, true_branch, false_branch)` can be used. However, this function requires knowledge about existing states and may require to add new states manually. To provide a more friendly interface, conditional execution can be programmed using the context managers for control structures:

  - `engine.condition(condition)`, `engine.else_condition()`: To realize a if-else behavior
  - `engine.for_loop(start, stop, increment)`: For-Loop
  - `engine.while_loop(condition)`: While loop

Under the hood, these context managers use the afforementioned `jump_if` and deal internally with state mingling to keep this complexity away from the user.

#### Internals
The `engine.states` collection is not merely a list -- it's the *only* source of truth for all states. This design ensures that any modification (adding, removing, or changing states) is reflected consistently across all generated code. When a new state is added via `engine.add_state("NEW_STATE")`, the state immediately becomes available for transition definition and assignment configuration. This eliminates the need for manual synchronization across multiple files, which is a common source of errors in traditional RTL development.

#### Signal Management

The signal and register management is done by the `SignalManager` and `ScratchManager` classes. These hold lists of signal objects that are currently declared.
Contrary to verilog, a new register may be declared at every position in the code -- The `engine` class cares about shifting the declarations to the appropriate positions in the resulting code.

To introduce a new signal or register to the circuit, the engine provides factory methods:

  - `engine.define_input(name: str, width: int)`. Creates an input signal. The name has to be a verilog identifier.
  - `engine.define_output(name: str, width: int, reset_value: int = 0)`: Defines a register that is connected to an output signal.
  - `engine.define_local(name: str, width: int, reset_value: int = 0)`: Creates a register without connection to the outside world.
  - `engine.define_scratch(width: int)`: Returns a scratch register. This signal is a part of an internal multi-purpose register bank and can be used like a normal register until it is released. After release, the signal may be used by a next routine. Note that these registers are released automatically, when exiting the context manager where they were defined.

For details about signal management, please find the special sections (once available).

#### Modules & Instances -- Integration of Verilog Modules

- **Instances**: ...


### States: Execution Units with Built-in Logic

States in noRTL are not just named entities—they are full execution units with their own logic. Each `State` object contains:

- **Assignments**: ...
- **Transitions**: ...
- **Prints** ...


### Parallel Behavior with Workers and Threads
...

### Metadata for Objects
...

### The `Renderable` Concept

The `Renderable` interface (not explicitly shown in the provided code but implied by the structure) is critical for the data model's flexibility. It allows different components (like signals, states, assignments) to be converted to their HDL representation consistently. For example, the `Signal` class implements a `render()` method that returns the appropriate Verilog representation.

Along this way, constants are automatically combined on python level to make life of the synthesis flow easier. This is also used to clean out conditional transitions that are always on.

This concept enables the system to handle complex expressions and signals uniformly, whether they're simple assignments or nested structures.

#### Built-in Operations

Renderable objects can be used in built-in arithmetic or logic operations, comparisons, sliced, and more.
Performing one of the supported operations will return a new Renderable object.

The following operations are supported:

```ebnf
operation               = two side operation | single operation | slice operation

(* Two Side operations are based on two operands, of which at least one must be a Renderable. "*)
two side operation      = left side operation | right side operation
left side operation     = Renderable, twoside operator, (Renderable | int | bool)
right side operation    = (int | bool), twoside operator, Renderable
twoside operator        = arithmetic operator | logic operator | comparison operator
arithmetic operator     = "+" | "-" | "*" | "/" | "%"
logic operator          = "&" | "|" | "^" | "<<" | ">>"
comparison operator     = "==" | "!=" | "<" | "<=" | ">" | ">="

(* Single operations modify a Renderable. *)
single operation        = modificator, Renderable
modificator             = "+" | "-" | "~"

(* Slice operations extract a single, or a range of bits from the operand. *)
slice operation         = Renderable, "[", start, [":", stop], "]"
start                   = int
stop                    = int
```

The goal of noRTL is to support (most of) the same operations as integers do in Python and allow intuitive coding.

As the result of the operation is a Renderable object, it can be stored in a Python variable, or directly used as an argument for a function expecting a Renderable.

```python
# Save operation result in a variable
var = adr + 1

# Use operation result as an function argument
engine.set(OUT, (a + << 8) | b)
```
