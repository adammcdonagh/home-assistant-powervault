# Home Assistant Powervault

> [!WARNING] > **Action required if upgrading from a previous version.**
> Powervault have sunset the legacy cloud API for P3 units. After upgrading this integration, Home Assistant will mark it as requiring reconfiguration and you **must** complete the steps below before it will resume working.
>
> - **P3 owners:** you will be asked to confirm your model and enter the local IP address of your unit. Ensure your Powervault P3 is reachable on your local network before proceeding.
> - **P4/P5 owners:** you will be asked to confirm your model. Your existing API key remains valid and no other changes are needed.

![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.powervault.total)

This custom component for Home Assistant allows you to monitor the status of your Powervault P3, P4 or P5 battery. This uses the _paid_ API offered by Powervault. To obtain an API key, you first need to contact Powervault directly and pay for access. This integration is useless without it.

Based on the Swagger docs hosted at https://app.swaggerhub.com/apis-docs/Powervault/PowervaultP3/

This integration has been confirmed as working with P3 & P5 batteries. P4 should work just the same based on the API specs.

### HACS

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration can be installed directly via HACS. To install:

- [Add the repository](https://my.home-assistant.io/redirect/hacs_repository/?owner=adammcdonagh&repository=home-assistant-powervault&category=integration) to your HACS installation
- Click `Download`

## Home Assistant Setup

1. Go to `Settings > Devices & Services > Add New` and select Powervault
2. Enter the API key and click submit.
3. Give your unit a name, and select the Unit ID from the list, if you only have one battery, click on the one that's listed
4. Your battery should now be added as a new device

## Battery Status Override

**⚠ WARNING: Changing battery status**

_IMPORTANT_ Changing the battery status will override any schedule you have have configured in the Powervault portal. The override sets the battery to that status for the next 24hrs. Only change the status if you are controlling it using Home Assistant only and don't want to use the scheduler in the Powervault portal

## Polling interval (Legacy P3 only)

P3 units communicate over your local network, so the integration can poll much more frequently than the cloud API. The default is **30 seconds**, and you can adjust this between **10 and 60 seconds** via the integration's **Configure** button in `Settings > Devices & Services`.

> [!WARNING] > **Avoid setting the polling interval too low without configuring the recorder.**
> Every poll produces a new state for each Powervault sensor. At 10-second intervals that is up to **8,640 state changes per sensor per day**. Be aware this will rapidly inflate your database. Before reducing the interval below the default, consider either:
>
> - Excluding the Powervault entities from the recorder in your `configuration.yaml`:
>   ```yaml
>   recorder:
>     exclude:
>       entity_globs:
>         - sensor.powervault_*
>   ```
> - Or only including the specific sensors you actually need in long-term history.
