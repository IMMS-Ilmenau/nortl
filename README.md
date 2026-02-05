# noRTL - Hardware design beyond register transfer level

**noRTL** (Not-only RTL) is a Python-based code generation framework for designing and implementing hardware description language (HDL) modules, particularly SystemVerilog state machines. It provides a high-level, Pythonic API for describing sets of finite state machines (FSMs) and hardware components with built-in correctness guarantees.

**noRTL** aims to make the design of complex digital systems easier by reducing the shortcommings of current hardware description languages that use the register transfer level (RTL) to model digital circuit's behavior. This tool goes beyond this level of abstraction: We digital designers want to describe behavior with cycle-level accuracy but do not want do deal with the complexity of state naming, state coding, starting parallel processes, etc. **noRTL** realizes this tedious part of digital design inside its core.

The code that is written for **noRTL** is pure Python code. The **noRTL** package realizes state handling and data structure assembly for you while the Python code is executed. **noRTL** can be understood as a fancy generator that assembles state machines and provides the tooling to render it to SystemVerilog and tools for verifying your code.

## Main ideas

**noRTL** is built with the following concepts and ideas.

* Each hardware description is an executable Python program. The hardware structure is assembled during execution. There is no need for static code analysis or parsing.
* There should be no need to declare states explicitely. The number of states is determined during execution of the code.
* The behavior description should be easily readable and feel procedural. Control structures should work similar to Python equivalents.
* Checks and Optimizations are to be done during runtime of the Python code. Post-Optimization has not been necessary (yet).

## Installation

A prerequisite for noRTL is the availablility of icarus Verilog in your path. This can be installed using your system's package manager or using the *oss-cad-suite* (https://github.com/YosysHQ/oss-cad-suite-build)

### Method 1: Using pip (Public Registry)

```bash
# Install nortl
pip install nortl
```

### Method 2: Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/IMMS-Ilmenau/nortl
cd nortl

# Install dependencies
uv sync

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Method 3: Development Installation

For development work, install in editable mode:

```bash
# Clone the repository
git clone https://github.com/IMMS-Ilmenau/nortl
cd nortl

# Install development dependencies
uv sync --all-extras

# Activate the virtual environment
source .venv/bin/activate
```

---

## Your First State Machine

Let's create a simple state machine that toggles an output based on an input.

```python
from nortl import Engine, Const

# Create an engine with a module name -- Clock and reset signal is automatically included
engine = Engine("my_first_engine")

# Define input and output signals
enable = engine.define_input("enable", width=1)
output = engine.define_output("output", width=1, reset_value=0)

# Don't define states -- define behavior!
with engine.while_loop(Const(1)):
    engine.wait_for(enable == 1)
    engine.set(output, 1)
    engine.sync() # Wait one clock cycle
    engine.set(output, 0)
    engine.wait_for(enable == 0)

# Generate SystemVerilog code
from nortl.renderer import VerilogRenderer
renderer = VerilogRenderer()
verilog_code = renderer.render(engine)

print(verilog_code)
```

## Acknowledgement

The DI-Meta-X project where this software has been developed is funded by the German Federal Ministry of Research, Technology and Space under the reference 16ME0976. Responsibility for the content of this publication lies with the author.
