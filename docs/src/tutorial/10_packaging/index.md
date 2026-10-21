# Packaging a noRTL Engine as a Python Package

In the previous chapters you've learned how to describe hardware with noRTL — defining signals, wiring together control structures, spawning parallel threads, and testing your designs with `NoRTLTestBase`. But what happens when a design grows beyond a single script? How do you share it, version it, or integrate it into a larger system?

This chapter answers those questions by walking through the process of packaging a noRTL engine as a proper Python library. We'll cover project layout, dependency management, testing, and how to conveniently export your code for synthesis.

## Why Package Your Engine?

Before diving into the mechanics, it's worth understanding *why* packaging matters:

- **Reusability**: A packaged engine can be imported by other projects just like any Python library. You write the traffic light controller once, then use it in a robotics project, a simulation, or a production FPGA design.
- **Testability**: Packaging forces you to separate your design from its test harness. This separation makes it easier to write focused tests and keeps your codebase maintainable.
- **Synthesis integration**: When your tests pass, you need the generated Verilog for actual hardware. By tying Verilog export into your Python test flow, you ensure the artifact always reflects the last-tested design. This will later allow for an integration in CI/CD flows.
- **Dependency clarity**: A `pyproject.toml` makes it explicit what your design depends on (nortl itself, any custom Verilog IP, simulation tools). This matters when handing a project to a colleague or deploying it on a CI server.

This all seems pretty obvious for the average Python programmer but actually improves the situation for hardware developers. In many HDLs such as Verilog, there is no common notion of packaging along with tests and a connection to CI/CD flows. noRTL inherits all this from Python.

For creating Python packages for noRTL-based hardware, you have to decide, if you want the Python class itself to inherit from the noRTL Engine (it actually *is* an engine) or if you want to create a reuseable IP where the engine is passed along and kept within the module.

## Project Structure

A noRTL hardware package follows Python's standard layout conventions. Here's the structure we'll build:

```
traffic_light/
├── pyproject.toml              # Package metadata, dependencies, build config
├── README.md                   # Human-readable documentation
├── src/
│   └── traffic_light/
│       ├── __init__.py         # Public API — what users import
│       ├── engine.py           # Main engine class (the hardware description)
│       ├── controllers.py      # Subsystem classes (pedestrian, emergency logic)
│       └── verilog_ip/         # Custom Verilog IP (optional)
│           ├── counter.sv
│           └── __init__.py     # Registers custom modules with noRTL
└── tests/
    ├── __init__.py
    ├── conftest.py             # Shared pytest fixtures
    ├── test_engine.py          # Simulation tests using NoRTLTestBase
    └── test_artifacts.py       # Verilog export for synthesis flows
```

Let's break down *why* each piece exists:

- **`src/traffic_light/`**: The `src/` layout is a Python best practice. It prevents accidental imports of the local package during development and makes it clear what gets installed. Your engine lives here as regular Python code — no special runtime, no compilation step.
- **`controllers.py`**: Following the composition pattern from the [Class tutorial](../03_classes.md), subsystem logic lives in separate classes. Each class receives the `Engine` instance and manages its own signals. This keeps the main engine class focused on orchestration rather than implementation details.
- **`verilog_ip/`**: If your design uses custom Verilog modules (see [Verilog Integration](../07_verilog_integration.md)), they live here alongside the Python code that registers them. This keeps all hardware description — both Python-generated and hand-written Verilog — in one place.
- **`tests/test_engine.py`**: Simulation tests that verify behavioral correctness using `NoRTLTestBase` (from [Pytest](../06_pytest.md)). These run the generated Verilog through Icarus Verilog simulation.
- **`tests/test_artifacts.py`**: A separate test that *only* exports Verilog — no simulation. This produces files that synthesis tools (Yosys, Vivado, Quartus) can consume directly. More on this in [Test & Artifacts](02_testing_and_artifacts.md).
