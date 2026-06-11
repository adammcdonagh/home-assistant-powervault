# v1.3.0

### Added

- **Legacy P3 local API support.** P3 units can now be connected directly over your local network instead of the deprecated Powervault cloud API. During setup, select "Legacy P3" and enter your unit's local IP address. The integration validates the connection before saving.
- **Automatic migration for existing P3 users.** Existing config entries are migrated to schema version 2. After upgrading, Home Assistant will prompt you to confirm your model and (for P3 owners) enter your unit's local IP address. You many need to manually reload the integration after this step.
- **Configurable polling interval for Legacy P3.** A new **Configure** option (available via `Settings > Devices & Services`) lets you set the polling interval for P3 units between 10 and 60 seconds (default 30 s). Changes take effect immediately without restarting Home Assistant.
- **Today's energy totals from local chart data.** The P3 local path now fetches intraday chart data to calculate today's cumulative energy totals (kWh) for all channels, with last-known-value carry-forward to handle gaps in the data stream.

### Changed

- Config flow now starts with a model selector step (Legacy P3 / Newer Powervault) rather than going directly to the API key screen.
- `iot_class` for P3 entries is effectively `local_polling`; the cloud path is unchanged.
- The reauth flow now asks users to identify their model and, for P3 owners, to provide a local IP address instead of re-entering API credentials.
- Bump [powervaultpy](https://pypi.org/project/powervaultpy/) version to v1.1.3.

# v1.2.5

- Fix power sensor state class and add last_reset for HA Energy Card compatibility

# v1.2.4

- Bump [powervaultpy](https://pypi.org/project/powervaultpy/) version to v1.1.0

# v1.2.3

- Add HACS validation

# v1.2.2

- Bump version of powervaultpy. Reverts back to using old API for battery state changes

# v1.2.1

- Fix linting issues

# v1.2.0

- Bump version of powervaultpy, which now uses the new "v2" REST API
- Rework the handling of flakey data returned by the Powervault API. Immediately, every 5 minutes the initial values are blank. Instead of using the last value, we now use the previous value for anything that is None.
