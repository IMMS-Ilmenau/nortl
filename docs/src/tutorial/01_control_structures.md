# Control structures, Signals and the Scratch pad

In this chapter, we dive a little bit deeper into noRTLs feature set. noRTL encapsulates a lot of the complexity that is often needed to implement a digital circuit and map it to conventional programming concepts (or tries to make it look like these concepts).

## If-Then-Else

noRTL provides a natural way to describe conditional logic using Python's context managers. The `engine.condition(condition)` function takes a boolean signal (or any `Renderable` expression, i.e. an expression that can be transferred to verilog) and automatically handles the underlying state machine transitions.

```python
with engine.condition(start):
    engine.set(grinder_en, 1)
    engine.sync()
    engine.set(grinder_en, 0)
with engine.else_condition():
    pass
```

Under the hood, noRTL analyzes the condition and creates a new state for the `if` branch. If the condition is met, the engine transitions into this branch. When the context manager exits, noRTL automatically adds a transition back to the original state (or a designated final state) for the `else` case, ensuring the state machine remains deterministic.

You can chain multiple conditions to implement `if-elif-else` logic:

```python
with engine.condition(mode == 1):
    engine.set(output, 1)
    # ...

with engine.condition(mode == 2):
    engine.set(output, 2)
    # ...

with engine.else_condition():
    engine.set(output, 0)
    # ...
```

Take care that each `engine.condition` has to be connected to a `engine.else_condition`! Otherwise, the execution flow will stop until one of the condition is met!

## For Loops

noRTL provides a `for_loop` context manager that emulates the behavior of a standard Python `for` loop while automatically generating the necessary counter logic and state transitions for your hardware design.

```python
out = engine.define_output("LOOP_COUNTER_OUT", 8)
engine.sync()  # Move from reset

with engine.for_loop(0, 10, 2) as i:
    engine.set(out, i)
    engine.sync()
```

The context manager takes care of initializing a counter, comparing it against the stop value, and incrementing it on each iteration. It returns the counter signal (`i` in the example), which you can use directly within the loop body as a `Renderable` expression.

Key features of the `for_loop` construct:

* `start`: The initial value of the counter (inclusive).
* `stop`: The termination value (non-inclusive, matching Python's `range()` behavior).
* `step`: The increment value for each iteration (default: 1).
* `counter_width`: The bit-width of the internal counter register (default: 16). Ensure this width is sufficient to hold your `stop` value.

Internally, noRTL automatically allocates a scratch register for the counter and handles the state machine transitions required to evaluate the loop condition, execute the body, and update the counter. If you need multiple independent loops, noRTL's scratch manager ensures their counters are allocated safely without collisions.

!!! note

    Avoid modifying the loop counter variable inside the loop body. Changing the counter manually can lead to unpredictable state transitions and break the intended hardware behavior. Let the engine handle the counter updates automatically.

## While Loop

The `while_loop` context manager emulates the behavior of a standard Python `while` loop while automatically generating the necessary state transitions for your hardware design.

```python
out = engine.define_output("WHILE_COUNTER_OUT", 8, 0)
engine.sync()  # Move from reset

with engine.while_loop(out < 4):
    engine.set(out, out + 1)
    engine.sync()
```

The context manager evaluates the provided `condition` at the beginning of each iteration. If the condition evaluates to true (logic-1), the engine proceeds into the loop body. Once the condition becomes false, the engine automatically transitions to the loop's exit state, ensuring deterministic control flow.
