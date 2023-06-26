# Home Assistant Powervault

![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.powervault.total)

This custom component for Home Assistant allows you to monitor the status of your Powervault PV3 battery. This uses the _paid_ API offered by Powervault. To obtain an API key, you first need to contact Powervault directly and pay for access. This integration is useless without it.

### HACS

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration can be installed directly via HACS. To install:

* [Add the repository](https://my.home-assistant.io/redirect/hacs_repository/?owner=adammcdonagh&repository=homeassistant-powervault&category=integration) to your HACS installation
* Click `Download`

## Home Assistant Setup

1. Go to `Settings > Devices & Services > Add New` and select Powervault
2. Enter the API key and click submit.
3. Give your unit a name, and select the Unit ID from the list, if you only have one battery, click on the one that's listed
4. Your battery should now be added as a new device

## Battery Status Override

**⚠ WARNING: Changing battery status**

_IMPORTANT_ Changing the battery status will override any schedule you have have configured in the Powervault portal. The override sets the battery to that status for the next 24hrs. Only change the status if you are controlling it using Home Assistant only and don't want to use the scheduler in the Powervault portal
