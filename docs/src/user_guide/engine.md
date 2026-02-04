## Quick-Start Guide to Engine Class


The Engine class in `engine.py` allows you to write state machines in a procedural way. This guide will walk you through the key methods and how to use them to create a state machine.

### Define Registers and Ports

Before defining states, you need to define the registers and ports that your state machine will use. You can do this using the following methods:

* `define_input(name, width=1, data_type='logic')`: Define an input signal.
* `define_output(name, width=1, reset_value=0, data_type='logic')`: Define an output signal.
* `define_local(name, width=1, data_type='logic')`: Define a local signal.

Example:
```python
engine = Engine('my_engine')
input_signal = engine.define_input('input_signal')
output_signal = engine.define_output('output_signal', reset_value=1)
local_signal = engine.define_local('local_signal')
```

### Using your Engine
After you constructed your engine and created ports and signals, you can start with creating the sequential behavior.
Since an example is more illustrative than just function description, consider a fully automated coffee machine with the following (simplified) interface:

* Inputs:
    * `REQUEST_COFFEE`: brew a normal coffee
    * `REQUEST_ESPRESSO` : to brew an espresso
* Outputs:
    * `GRINDER_EN`: Enable / disable the coffee grinder
    * `PUMP_EN`: Enable / disable the water pump
    * `HEATER_EN`: Enable / disable the water heater
    * `PRESSURE[3:0]`: Select the pressure for the brewing process

We want to realize the following processes:

* To brew a coffee, we need to switch on the grinder for 2 seconds and then switch on the heater. The heater needs an additional second to start and then we start the water flow by setting `PUMP_EN` for 10 seconds with low pressure (`PRESSURE=1`).
* To brew an espresso, we need to switch on the grinder for 3 seconds and then switch on the heater. The heater needs an additional second to start and then we start the water flow by setting `PUMP_EN` for 2 seconds with high pressure (`PRESSURE=15`).

Now, we can create our hardware controller:

```python

from nortl import engine
from nortl.core.constructs import Condition
from nortl.renderer.verilog_renderer import VerilogRenderer
from nortl.components import Timer

engine = Engine('my_engine')
coffee = engine.define_input('REQUEST_COFFEE')
espresso = engine.define_input('REQUEST_ESPRESSO')
grinder = engine.define_output('GRINDER_EN', reset_value=0)
pump = engine.define_output('PUMP_EN', reset_value=0)
heater = engine.define_output('HEATER_EN', reset_value=0)
pressure = engine.define_output('GRINDER_EN', reset_value=0, width=4)

timer = Timer(engine)

# we need to know our clock frequency to realize the delays
fclk = 1e6
```

After we created the engine, we are in reset state and can start by describing the behavior:

```python
# ...

with Condition(coffee.rising()): # coffee.rising() automatically created the edge detector
    # Grind Coffee
    engine.set(grinder, 1)
    timer.wait(fclk*2)
    engine.set(grinder, 0)

    # Pre-Heating Phase
    engine.set(heater, 1)
    timer.wait(fclk*1)

    # Brew!
    engine.set(pressure, 1)
    engine.set(pump, 1)
    timer.wait(fclk*10)

    # Reset our signals and go back to reset
    engine.set(pressure, 0)
    engine.set(pump, 0)
    engine.set(heater, 0)

with Condition(espresso.rising()):
    # similar procedure as above for brewing coffee

# Go back to reset state (once the devs created a while loop, this will look less nasty)
engine.jump_if(Const(1), engine.reset_state)
```

After we described our behavior, we can just write out the verilog code:
```python
renderer = VerilogRenderer(engine)
with open('coffee_engine.sv', 'w') as file:
    file.write(renderer.render())
```


## Additional Information

### Naming States

States are automatically created by the `sync()` and `wait_for()` methods. However, you can name the initial state using the `reset_state_name` parameter when creating the engine instance:
```python
engine = Engine('my_engine', reset_state_name='IDLE')
```
Alternatively, you can name the next state after calling `next_state`:
```python
engine.next_state  # Create a new state
engine.current_state = engine.next_state  # Set the current state to the new state
```
Note that states are automatically named by the engine if you don't provide a name.

### Create Events

Events are used to trigger transitions between states. You can create events using the following methods:

* `rising(signal)`: Create a rising edge event on the given signal.
* `falling(signal)`: Create a falling edge event on the given signal.
* `delayed(signal, cycles=1)`: Create a delayed event on the given signal.
* `synchronized(signal)`: Create a synchronized event on the given signal.

Example:
```python
event_signal = engine.rising(input_signal)
```
You can use the created event signal as a condition for a transition.

### Transitions

Transitions are created using the following methods:

* `sync()`: Synchronize outputs and move to the next state.
* `wait_for(condition)`: Wait until the given condition is met and then move to the next state.
* `jump_if(condition, true_state, false_state=None)`: Jump to the given state if the condition is met, otherwise stay in the current state.

Example:
```python
engine.set(output_signal, 1)  # Set output signal to 1
engine.sync()  # Synchronize outputs and move to the next state

engine.wait_for(event_signal)  # Wait until the event signal is high
engine.set(output_signal, 0)  # Set output signal to 0
engine.sync()  # Synchronize outputs and move to the next state
```
Note that you can use the `next_state` attribute to create a new state and set it as the current state.

## Additional Tips

* Use `set_once()` to set a signal for the current state and reset it in the next state.
* Use `set()` to set a signal for the current state without resetting it in the next state.
* Use `jump_if()` to create conditional transitions between states.

By following these guidelines, you can create complex state machines using the engine class in a procedural way. Remember to use the provided methods to define registers and ports, create events, and create transitions between states.
