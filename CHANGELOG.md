# v2.0.1

**NOTE** If Powervault local data is lost in the 1st 24 hrs of updating, the data may be incorrect. Data is collected in case of Powervault history failure from midnight. This will correct itself at midnight.

### Fixed

- **Energy total sensors no longer reset mid-day.** The root cause was a combination of two issues: the `TOTAL_INCREASING` state class (which treats any decrease as a meter rollover) and a reliance on the Powervault API returning a full day of chart history on every poll. Powervault's history API loses data unpredictably, causing totals to drop to zero and never recover until midnight.

### Changed

- Bumped `powervaultpy` to `v1.1.4`
- **Hybrid incremental accumulator for P3 energy totals.** Rather than recalculating totals from scratch using the full-day chart history on every poll, the integration now maintains a running accumulator. Each poll, a small energy delta (watts × elapsed time) is added to the accumulator using the current instantaneous readings. The API chart history is still fetched and used as a cross-check — if the API returns a value higher than the accumulator (normal operation), the more accurate API value is used. If the API value drops below the accumulator (history reset), the API value is ignored and the accumulator carries on uninterrupted.
- **Accumulator is persisted across Home Assistant restarts.** The running daily total is saved to HA's `.storage/` directory after every poll. On startup, the saved value is restored if it is from the current day, so a restart no longer causes totals to reset to zero mid-day.
- **Energy total sensor state class changed from `TOTAL_INCREASING` to `TOTAL`.** The previous class caused HA to misinterpret any decrease in value as a utility meter rollover. `TOTAL` correctly models a daily accumulation that resets at midnight.

### Added

- **"Use API History" switch (Legacy P3 only).** A new switch entity — `switch.powervault_use_api_history` — lets you disable the API chart history fetch entirely, forcing the integration to rely solely on the incremental accumulator. Useful if the Powervault history API is consistently unreliable on your unit. The switch is on by default and the setting persists across restarts.

# v2.0.0

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
