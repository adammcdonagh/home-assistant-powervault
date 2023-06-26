# Powervault Custom Component for Home Assistant

This custom component for Home Assistant allows you to monitor the status of your Powervault PV3 battery. This uses the _paid_ API offered by Powervault. To obtain an API key, you first need to contact Powervault directly and pay for access. This integration is useless without it.

## Home Assistant Setup

1. Install this repository using [HACS](https://hacs.xyz) (add this repo as a Custom Repository).
2. Go to `Settings > Devices & Services > Add New` and select Powervault
3. Enter the API key and click submit.
4. Give your unit a name, and select the Unit ID from the list, if you only have one battery, click on the one that's listed
5. Your battery should now be added as a new device

## Battery Status Override

**⚠ WARNING: Changing battery status**

_IMPORTANT_ Changing the battery status will override any schedule you have have configured in the Powervault portal. The override sets the battery to that status for the next 24hrs. Only change the status if you are controlling it using Home Assistant only and don't want to use the scheduler in the Powervault portal
