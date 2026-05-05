# Using Python classes and packages for organizing your code

As your hardware designs grow in complexity, keeping all state transitions, signal definitions, and timing logic in a single script quickly becomes unmanageable. noRTL embraces Python's native object-oriented features, allowing you to structure your designs into modular, reusable components without sacrificing the sequential, hardware-like feel of your code.

## Inheriting from the Engine class
While you don't *need* to inherit from `Engine` to use noRTL, doing so can be useful when you want to create custom engine variants with predefined initialization logic, default parameters, or custom rendering hooks.

```python
from nortl import Engine

class CustomEngine(Engine):
    def __init__(self, module_name: str):
        # Call the parent constructor
        super().__init__(module_name)

        # You can add custom initialization here
        self.define_parameter("CLK_DIV", default_value=1)
        self.define_local("DEBUG_FLAG", width=1, reset_value=0)
```

In most cases, however, **composition** is preferred over inheritance. Creating separate classes that manage specific subsystems and passing the `Engine` instance to them keeps your code flexible and easier to test.

## Encapsulate your glue logic in functions and classes
noRTL's context managers and state transitions are tied to the active `Engine` instance. This means you can safely encapsulate hardware logic inside Python functions or classes. As long as you pass the `engine` reference, the underlying state machine will correctly stitch everything together.

For example, let's encapsulate the heater control logic from our coffee machine into a reusable class:

```python
class HeaterController:
    def __init__(self, engine: Engine, heater_en: Signal):
        self.engine = engine
        self.heater_en = heater_en

    def activate(self, duration_cycles: int):
        """Turn on the heater and wait for a specified duration."""
        self.engine.set(self.heater_en, 1)
        self.engine.sync()  # Ensure clean state transition
        self.engine.timer.wait_delay(duration_cycles)
        self.engine.set(self.heater_en, 0)
```

Now, in your main script, you can instantiate and use this controller cleanly:

```python
engine = Engine("CoffeeMachineV2")
heater_en = engine.define_output("HEATER_EN", 1, 0)
timer = Timer(engine, 24)

# Instantiate our reusable controller
heater_ctrl = HeaterController(engine, heater_en)

with engine.while_loop(Const(True)):
    engine.wait_for(start.rising())
    heater_ctrl.activate(fclk * 5)  # Heat for 5 seconds
    # ... rest of the logic ...
```


!!! note
    Please take care that there are no naming collisions in the verilog signal names when you create local signals inside your classes. This can be circumvented by appending e.g. unique numbers or prefixes to your verilog signal names -- or using scratch variables.


## Structural Idea
When organizing larger designs, think of your `Engine` as the top-level module and your Python classes as IP blocks or subsystem controllers. A typical structure looks like this:

1. **Interface Definition:** Define all ports and top-level signals in the main script.
2. **Subsystem Classes:** Create classes for independent functional blocks (e.g., `PumpController`, `Grinder`, `ArithmeticUnit`).
3. **Signal Scoping:** Use `engine.define_local()` or `engine.define_scratch()` inside your classes for internal state. This keeps the top-level interface clean and prevents naming collisions.
4. **Top-Level Wiring:** Instantiate your classes in the main script and connect their inputs/outputs using `engine.set()` or direct signal references.

This approach mirrors standard hardware design practices: you design, verify, and reuse blocks, then integrate them into a cohesive system.

## Re-Use of functions using classes
To make your designs truly reusable, parameterize your classes. This is especially useful when you need to instantiate multiple identical hardware blocks with different configurations.

```python
class Counter:
    def __init__(self, engine: Engine, name: str, width: int = 8, max_val: int = 100):
        self.count = engine.define_local(name, width=width, reset_value=0)
        self.max_val = max_val
        self.engine = engine

    def reset_and_increment(self):
        self.engine.set(self.count, 0)
        self.engine.sync()
        with self.engine.while_loop(self.count < self.max_val):
            self.engine.set(self.count, self.count + 1)
            self.engine.sync()
```

By keeping classes lightweight and stateless (except for the signals they manage), you avoid complex inheritance hierarchies that can make debugging state transitions difficult. Instead, favor composition: your main `Engine` script acts as the "top-level module", instantiating and connecting various controller classes.
