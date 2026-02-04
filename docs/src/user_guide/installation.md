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
