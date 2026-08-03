# NIBE Greenline LWSE-V for Home Assistant

A Home Assistant custom integration for NIBE Greenline LWSE-V heat-pump controllers (formerly KNV). It provides local control and monitoring through the controller's MControl2 WebSocket interface.

> [!WARNING]
> This community integration uses an undocumented protocol reverse-engineered from the controller web interface. Controller firmware updates may change or remove that interface. The integration has been tested with controller/web-app version 1.3.

## Features

- Local push updates through a persistent WebSocket connection; no polling.
- Automatic recovery after transport failures, with subscriptions restored after reconnecting.
- A `climate` entity for HK1 current/target temperature and `off`, `heat`, `cool`, and `heat_cool` modes.
- A `number` entity for the HK1 reduced (economy/setback) target temperature.
- Sensors for WW1 current and target temperatures.
- UI configuration, connection validation, and reauthentication after credential changes.
- Stable device and entity identifiers based on the controller serial number.

## Limitations

- Only heating circuit 1 (HK1) and warm-water circuit 1 (WW1) are currently implemented. Additional circuits should be straightforward to add, but they are not used in the developer's home and therefore could not be tested.
- The protocol client is controller-specific because no maintained public MControl2 client library is available.
- Transport failures are retried after a fixed 30-second delay. Authentication failures require reauthentication and are not retried automatically.

## Installation

### HACS

1. In HACS, add this repository as a custom repository of category **Integration**.
2. Install **NIBE Greenline LWSE-V**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/greenline_lwse_v` into the Home Assistant configuration directory so that it is available at `config/custom_components/greenline_lwse_v/`, then restart Home Assistant.

## Configuration

In Home Assistant, go to **Settings → Devices & services → Add integration**, select **NIBE Greenline LWSE-V**, and enter the controller host or IP address plus the credentials used for its web interface. Home Assistant must be able to reach the controller over HTTP and WebSocket port 3118.

## Entities

| Entity                        | Platform  | Description                                   |
| ----------------------------- | --------- | --------------------------------------------- |
| Heating circuit 1             | `climate` | Current/target room temperature and HVAC mode |
| Reduced room temperature      | `number`  | HK1 reduced (economy/setback) target          |
| Warm water temperature        | `sensor`  | WW1 current temperature                       |
| Warm water target temperature | `sensor`  | WW1 target temperature                        |

## Development

[uv](https://docs.astral.sh/uv/) is the sole dependency manager. The committed `uv.lock` provides a reproducible Python and tool environment.

```bash
uv sync --locked --all-groups
./validate.sh
```

`./validate.sh` verifies the lockfile, checks version consistency, runs all pre-commit hooks (including strict mypy checks), and runs the complete test suite with coverage. For a focused test, invoke pytest through the locked test group:

```bash
uv run --locked --group test pytest tests/test_config_flow.py -k reauth
```

To run strict type checks directly, use the uv-managed mypy version from `pyproject.toml` and `uv.lock`:

```bash
uv run --locked --group quality --group test mypy --config-file=mypy.ini custom_components/greenline_lwse_v
```

Dependency versions are pinned for reproducibility. Dependabot updates uv and GitHub Actions dependencies, while pre-commit.ci updates hook revisions. To refresh all direct development dependencies and pre-commit hooks manually before validating, run:

```bash
./validate.sh --update
```

To build a validated HACS-compatible archive for the version declared in the manifest:

```bash
./create-release.sh
```

Use `--skip-validation` only if the same checkout has already passed `./validate.sh`.

## License and attribution

This integration is distributed under the [Apache License 2.0](LICENSE.md).

The NIBE icon is sourced from the [Home Assistant brands repository](https://github.com/home-assistant/brands/tree/master/core_integrations/nibe_heatpump) and is used only to identify compatible products. NIBE and KNV names and trademarks belong to their respective owners. This unofficial community integration is not affiliated with or endorsed by NIBE, KNV, or Home Assistant.
