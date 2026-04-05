"""Platform for sensor integration."""

from __future__ import annotations

import warnings
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import slugify

from .api_renpho import _LOGGER
from .const import (
    CONF_REFRESH,
    CONF_UNIT_OF_MEASUREMENT,
    DOMAIN,
    KG_TO_LBS,
    MASS_KILOGRAMS,
    MASS_POUNDS,
)
from .coordinator import create_coordinator
from .sensor_configs import sensor_configurations

warnings.filterwarnings("ignore", message="Setup of sensor platform renpho is taking over 10 seconds.")


async def sensors_list(
    hass: HomeAssistant, config_entry: ConfigEntry, coordinator
) -> list[RenphoSensor]:
    """Return a list of sensors, initialized with the coordinator."""
    return [
        RenphoSensor(coordinator, **sensor, unit_of_measurement=hass.data[CONF_UNIT_OF_MEASUREMENT])
        for sensor in sensor_configurations
    ]


async def async_setup(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator = create_coordinator(hass, hass.data[DOMAIN], config_entry)
    await coordinator.async_config_entry_first_refresh()
    sensor_entities = await sensors_list(hass, config_entry, coordinator)
    async_add_entities(sensor_entities, update_before_add=True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator = create_coordinator(hass, hass.data[DOMAIN], config_entry)
    await coordinator.async_config_entry_first_refresh()
    sensor_entities = await sensors_list(hass, config_entry, coordinator)
    async_add_entities(sensor_entities, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
):
    """Set up the sensor platform asynchronously."""
    try:
        coordinator = create_coordinator(hass, hass.data[DOMAIN], discovery_info)
        await coordinator.async_config_entry_first_refresh()
        sensor_entities = await sensors_list(hass, config, coordinator)
        async_add_entities(sensor_entities, update_before_add=True)
    except ConnectionError as ex:
        _LOGGER.error("Error: %s", ex)
        return False


class RenphoSensor(SensorEntity):
    """Representation of a Renpho sensor."""

    def __init__(
        self,
        coordinator,
        id: str,
        name: str,
        unit: str,
        category: str,
        label: str,
        metric: str,
        unit_of_measurement: str,
    ) -> None:
        """Initialize the sensor with the coordinator."""
        self.coordinator = coordinator
        self._metric = metric
        self._id = id
        self._name = f"Renpho {name}"
        self._unit = unit
        self._category = category
        self._label = label
        self._unit_of_measurement = unit_of_measurement
        self._timestamp = None
        self._attr_name = self._name
        self._attr_native_value = None
        self._apply_native_metadata()

        self.async_on_remove(coordinator.async_add_listener(self._schedule_update))

    def _apply_native_metadata(self) -> None:
        if self._id == "weight":
            self._attr_device_class = SensorDeviceClass.WEIGHT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = (
                UnitOfMass.POUNDS
                if self._unit_of_measurement == MASS_POUNDS
                else UnitOfMass.KILOGRAMS
            )
        elif self._unit == MASS_KILOGRAMS:
            self._attr_native_unit_of_measurement = (
                UnitOfMass.POUNDS
                if self._unit_of_measurement == MASS_POUNDS
                else UnitOfMass.KILOGRAMS
            )
        elif self._unit == "cm":
            self._attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
        elif self._unit:
            self._attr_native_unit_of_measurement = self._unit
        else:
            self._attr_native_unit_of_measurement = None

    def _schedule_update(self):
        """Schedule an update of the coordinator."""
        self.hass.async_add_job(self._handle_coordinator_update)

    async def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        await self.async_update()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"renpho_{slugify(self._name)}"

    @property
    def extra_state_attributes(self):
        return {
            "timestamp": self._timestamp,
            "category": self._category,
            "label": self._label,
        }

    @property
    def category(self) -> str:
        """Return the category of the sensor."""
        return self._category

    @property
    def label(self) -> str:
        """Return the label of the sensor."""
        return self._label

    async def async_update(self):
        """Request an immediate update of the coordinator data."""
        try:
            metric_value = await self.coordinator.api.get_specific_metric(
                metric_type=self._metric,
                metric=self._id,
                user_id=None,
            )

            if metric_value is not None:
                if self._unit == MASS_KILOGRAMS and self._attr_native_unit_of_measurement in (
                    UnitOfMass.POUNDS,
                    UnitOfMass.KILOGRAMS,
                ):
                    if self._attr_native_unit_of_measurement == UnitOfMass.POUNDS:
                        self._attr_native_value = round(float(metric_value) * KG_TO_LBS, 2)
                    else:
                        self._attr_native_value = round(float(metric_value), 2)
                elif isinstance(metric_value, float):
                    self._attr_native_value = round(metric_value, 2)
                else:
                    self._attr_native_value = metric_value
                self._timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _LOGGER.debug(
                    "Updated %s (%s) = %s",
                    self._name,
                    self._metric,
                    self._attr_native_value,
                )
            else:
                self._attr_native_value = None

        except (ConnectionError, TimeoutError) as e:
            _LOGGER.error(
                "%s while updating %s (%s): %s",
                type(e).__name__,
                self._name,
                self._metric,
                e,
            )

        except Exception as e:
            _LOGGER.exception(
                "Unexpected error updating %s (%s): %s",
                self._name,
                self._metric,
                e,
            )
