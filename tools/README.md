# Tools

This directory contains testing and development tools for the ML controller system.

## Testing Tools

### `test_bandwidth_control.py`
Manual bandwidth control testing tool for verifying controller behavior.

```bash
python3 test_bandwidth_control.py --help
```

### `test_decrease.py` 
Tool for testing bandwidth decrease scenarios and controller response.

```bash
python3 test_decrease.py
```

### `comprehensive_test.py`
Legacy comprehensive testing script. **Note:** This has been superseded by the organized test suite in `../tests/`.

**Recommendation:** Use `../tests/run_tests.py` instead for structured testing.

## Development Usage

These tools are intended for:
- Manual testing during development
- Debugging controller behavior
- Validating specific scenarios
- Performance testing

For automated testing, use the test suite in `../tests/` directory.