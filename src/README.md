# Source Code Structure

Python source code for the deterministic networking control system.

## Modules

### controller/
Main bandwidth control logic:
- `flow_manager.py` - Bandwidth controller with asymmetric AIMD algorithm
- `config_loader.py` - YAML configuration parser

### probes/
Network measurement components:
- `network_probe.py` - Active UDP/TCP latency and throughput prober
- `udp_server.py` - UDP echo reflector for jitter measurement

### exporters/
Metrics exporters:
- `bandwidth_exporter.py` - Exposes current bandwidth allocations to Prometheus

## Development

```bash
# Install dependencies
pip install -r requirements/requirements-dev.txt

# Run tests
pytest tests/ -v

# Check syntax
python3 -m py_compile src/controller/flow_manager.py
```

## Architecture

```
UDP/TCP Probes → Network Probe → Prometheus Metrics
                                       ↓
                                 Flow Manager
                                       ↓
                              K8s API (annotations)
                                       ↓
                              Cilium eBPF Enforcement
```
