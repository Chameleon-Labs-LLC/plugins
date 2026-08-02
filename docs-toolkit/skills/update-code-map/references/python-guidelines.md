# Python Code Map Guidelines

## File Header Format

```markdown
### [Module/Class Name]
**Path**: `path/to/module.py` - [line count] lines
**Purpose**: [Brief description]
**Language**: Python
```

## Documentation Structure

### For Modules (Python Files)

#### Module-Level Elements Table
```markdown
#### Module-Level Elements
| Element | Line | Type | Description |
|---------|------|------|-------------|
| CONSTANT_NAME | 12 | constant | Configuration constant |
| global_var | 15 | variable | Global state variable |
```

#### Imports Section
```markdown
#### Imports
| Import | Line | Type | From |
|--------|------|------|------|
| sys | 1 | stdlib | - |
| Path | 3 | stdlib | pathlib |
| QMainWindow | 5 | external | PyQt6.QtWidgets |
| custom_module | 8 | local | .core.utils |
```

### For Classes

#### Properties Table
```markdown
#### Properties
| Property | Line | Type | Access | Description |
|----------|------|------|--------|-------------|
| _private_var | 45 | str | private | Internal state |
| public_var | 47 | int | public | Public counter |
| class_var | 42 | dict | class | Shared configuration |
```

#### Methods Table
```markdown
#### Methods
| Method | Line | Type | Returns | Async | Description |
|--------|------|------|---------|-------|-------------|
| __init__ | 50 | constructor | None | No | Initialize instance |
| process_data | 65 | public | dict | No | Main processing |
| _internal_helper | 95 | private | str | No | Internal helper |
| async_operation | 110 | public | Awaitable[Result] | Yes | Async operation |
| @classmethod load | 130 | class | Self | No | Factory method |
| @staticmethod validate | 145 | static | bool | No | Validation utility |
| @property status | 160 | property | str | No | Computed property |
```

### For Functions (Module-Level)

```markdown
#### Functions
| Function | Line | Scope | Returns | Async | Description |
|----------|------|-------|---------|-------|-------------|
| main | 200 | public | int | No | Entry point |
| _private_helper | 225 | private | str | No | Internal helper |
| async async_task | 250 | public | None | Yes | Background task |
```

### For Data Classes / NamedTuples / TypedDicts

```markdown
#### Data Structures
| Name | Line | Type | Fields |
|------|------|------|--------|
| UserConfig | 15 | @dataclass | name, email, preferences |
| Point | 28 | NamedTuple | x: float, y: float, z: float |
| ApiResponse | 35 | TypedDict | status, data, errors |
```

### For Decorators and Context Managers

```markdown
#### Decorators
| Decorator | Line | Purpose |
|-----------|------|---------|
| @retry | 100 | Automatic retry logic |
| @cache | 120 | Result caching |

#### Context Managers
| Manager | Line | Purpose |
|---------|------|---------|
| DatabaseConnection | 150 | Database session management |
| FileHandler | 175 | Safe file operations |
```

## Python-Specific Patterns to Document

### 1. Magic Methods
Document all `__dunder__` methods with their purpose:
- `__init__`, `__new__` - Construction
- `__str__`, `__repr__` - String representation
- `__eq__`, `__hash__` - Comparison
- `__enter__`, `__exit__` - Context manager
- `__call__` - Callable objects
- `__getitem__`, `__setitem__` - Container protocol

### 2. Property Decorators
```markdown
| Property | Line | Type | Setter | Deleter | Description |
|----------|------|------|--------|---------|-------------|
| @property name | 45 | str | Yes | No | User name accessor |
| @property status | 60 | str | No | No | Read-only status |
```

### 3. Class vs Instance vs Static Methods
Clearly distinguish:
- **Instance methods**: Regular methods with `self`
- **Class methods**: `@classmethod` with `cls`
- **Static methods**: `@staticmethod` with no implicit first arg

### 4. Type Hints
Include type information from annotations:
```markdown
| Method | Line | Signature | Returns |
|--------|------|-----------|---------|
| process | 45 | (self, data: dict[str, Any]) | list[Result] |
| validate | 60 | (value: str, pattern: re.Pattern) | bool |
```

### 5. Async/Await Patterns
Mark async functions and show their awaitable return types:
```markdown
| Function | Line | Returns | Async | Await Pattern |
|----------|------|---------|-------|---------------|
| fetch_data | 100 | Awaitable[dict] | Yes | Single await |
| process_batch | 125 | AsyncGenerator[Item] | Yes | Async iteration |
```

### 6. Generators and Iterators
```markdown
| Generator | Line | Yields | Type |
|-----------|------|--------|------|
| read_chunks | 75 | bytes | Generator |
| async stream_data | 95 | dict | AsyncGenerator |
```

## Python Project Structure Patterns

### Standard Package Layout
```
project/
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── __main__.py       # Entry point
│       ├── core/             # Core modules
│       ├── utils/            # Utilities
│       └── tests/            # Tests
├── pyproject.toml            # Modern Python packaging
├── setup.py                  # Legacy packaging
├── requirements.txt          # Dependencies
└── README.md
```

### Application Layout (Non-Package)
```
app/
├── main.py                   # Entry point
├── config.py                 # Configuration
├── models/                   # Data models
├── services/                 # Business logic
├── gui/                      # UI components
├── cli/                      # CLI interface
└── tests/                    # Test suite
```

## Common Python Idioms to Document

### 1. Context Managers
```python
with open(file) as f:
    ...
```
Document: "Uses context manager for automatic resource cleanup"

### 2. List/Dict/Set Comprehensions
```python
result = [x for x in items if x > 0]
```
Document line numbers where complex comprehensions are used

### 3. Unpacking and Multiple Assignment
```python
x, y, *rest = values
```
Note where this pattern is used for clarity

### 4. Decorators
Document all custom decorators and their effects on wrapped functions

## Virtual Environment Documentation

Always document the virtual environment setup:
```markdown
## Python Environment

### Virtual Environments
- **Development (Windows/PowerShell)**: `.venv/`
  - Activation: `.\.venv\Scripts\Activate.ps1`
  - Python Version: 3.12

- **Development (Linux/WSL)**: `.venv_linux/`
  - Activation: `source .venv_linux/bin/activate`
  - Python Version: 3.x

### Dependencies
- Core: Listed in `requirements.txt`
- Dev: Listed in `requirements-dev.txt` (if exists)
- Package management: pip / poetry / conda
```

## Python Configuration Files

Document these Python-specific config files:
- `pyproject.toml` - Modern packaging and tool configuration
- `setup.py` / `setup.cfg` - Legacy packaging
- `requirements.txt` - Pip dependencies
- `Pipfile` / `Pipfile.lock` - Pipenv dependencies
- `poetry.lock` - Poetry dependencies
- `tox.ini` - Testing automation
- `pytest.ini` / `setup.cfg` - Pytest configuration
- `.pylintrc` / `pyproject.toml` - Linting configuration
- `mypy.ini` / `pyproject.toml` - Type checking configuration

## Performance and Optimization Notes

Document these patterns when found:
- **Slots**: `__slots__` usage for memory optimization
- **Caching**: `@lru_cache`, `@cache` decorators
- **Lazy loading**: Properties that defer expensive operations
- **Generator expressions**: Memory-efficient iteration
- **Multiprocessing**: Parallel processing patterns
