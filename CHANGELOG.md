# v1.2.3

- Add HACS validation

# v1.2.2

- Bump version of powervaultpy. Reverts back to using old API for battery state changes

# v1.2.1

- Fix linting issues

# v1.2.0

- Bump version of powervaultpy, which now uses the new "v2" REST API
- Rework the handling of flakey data returned by the Powervault API. Immediately, every 5 minutes the initial values are blank. Instead of using the last value, we now use the previous value for anything that is None.
