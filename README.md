# Greenline LWSE-V for Home Assistant

A Home Assistant custom integration for Greenline LWSE-V heat-pump controllers using the MEC Electronics MControl2 web interface. It provides local control of heating circuit 1 (HK1) and monitoring for warm-water circuit 1 (WW1).

> [!WARNING]
> This community integration uses an undocumented WebSocket protocol reverse-engineered from the controller web interface. A controller firmware update can change or remove that interface. It has been tested with controller/web-app version 1.3.

## Features

- Local push updates through a persistent WebSocket connection; no polling.
- A `climate` entity for HK1 current/target temperature and `off`, `heat`, `cool`, and `heat_cool` modes.
- A `number` entity for the HK1 reduced (economy/setback) target temperature.
- Sensors for WW1 current and target temperatures.
- UI configuration, connection validation, and reauthentication after credential changes.
- Stable device and entity identifiers based on the controller MAC address.

## Limitations

- Only HK1 and WW1 are supported.
- The controller does not expose a serial number through this protocol. Setup resolves its MAC address, so Home Assistant and the controller must share a network segment where MAC discovery is possible.
- The integration has no cloud or remote-access support.
- The embedded protocol client is controller-specific because no maintained public MControl2 client library is available.

## Installation

### HACS

1. In HACS, add this repository as a custom repository of category **Integration**.
2. Install **Greenline LWSE-V**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/greenline_lwse_v` into the Home Assistant configuration directory, resulting in `config/custom_components/greenline_lwse_v/`, then restart Home Assistant.

## Migration from the previous domain

This release changes the Home Assistant integration domain from `knv_greenline` to `greenline_lwse_v`. Home Assistant treats that as a new integration; existing entries are not migrated automatically. Before updating, note the current host and credentials. After updating, remove the old integration if it remains listed and add **Greenline LWSE-V** again from **Settings → Devices & services**. Entity IDs may change, so update dashboards, automations, scripts, and voice-assistant references as needed.

## Configuration

In Home Assistant, go to **Settings → Devices & services → Add integration**, select **Greenline LWSE-V**, and enter the controller host/IP address plus the credentials used for its web interface.

## Entities

| Entity | Platform | Description |
| --- | --- | --- |
| Heating circuit 1 | `climate` | Current/target room temperature and HVAC mode |
| Reduced room temperature | `number` | HK1 reduced (economy/setback) target |
| Warm water temperature | `sensor` | WW1 current temperature |
| Warm water target temperature | `sensor` | WW1 target temperature |

## Development

The test suite uses `pytest-homeassistant-custom-component` and requires Python **3.14.2 or later**. The pinned test environment currently uses the Home Assistant `2026.8.0b0` dependency required by that package version.

### UV workflow (recommended)

[uv](https://docs.astral.sh/uv/) manages the required Python version and locked dependencies without changing Ubuntu's system Python installation.

```bash
uv sync --group test
./run-tests.sh all
./run-tests.sh coverage
./validate.sh
```

`./validate.sh` runs pre-commit followed by the coverage suite and must be run from a Git checkout. Use `./create-release.sh 0.1.0` to validate and create a HACS-compatible archive, or pass `--skip-validation` only when checks have already run.

For focused work, pass normal pytest selectors through the helper script:

```bash
./run-tests.sh tests/test_config_flow.py -k reauth
```

### pip workflow with the host Python 3.14 interpreter

Do not replace Ubuntu's system `python3`. When a host-managed environment is needed, call `python3.14` explicitly:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_dev.txt
pytest tests -v
```

`requirements_dev.txt` is a pip-compatible, fully pinned export of `uv.lock`. Regenerate it after dependency changes with:

```bash
uv export --locked --group test --no-emit-project --format requirements-txt --no-hashes
```

To run strict type checks through UV:

```bash
uv run --group test --with mypy==1.19.1 mypy --config-file=mypy.ini custom_components/greenline_lwse_v
```

## License and attribution

This integration is distributed under the [Apache License 2.0](LICENSE.md).

It is an unofficial community integration and is not affiliated with or endorsed by Nibe, MEC Electronics, or any controller manufacturer.
