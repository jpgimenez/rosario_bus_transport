"""Support for Rosario information from https://comollego.rosario.gob.ar/.

For more info on the API see :
https://ws.rosario.gob.ar/ubicaciones/public/cuandollega
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta
from http import HTTPStatus

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

from .coordinator import RosarioBusDataUpdateCoordinator

_RESOURCE = "https://ws.rosario.gob.ar/ubicaciones/public/cuandollega"

ATTR_STOP_ID = "Stop ID"
ATTR_ROUTE = "Route"
ATTR_DUE_IN = "Due in"
ATTR_DUE_AT = "Due at"
ATTR_NEXT_UP = "Later Bus"

CONF_STOP_ID = "stopid"
CONF_ROUTE = "route"

DEFAULT_NAME = "Next Bus"

SCAN_INTERVAL = timedelta(minutes=1)
TIME_STR_FORMAT = "%H:%M"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_STOP_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_ROUTE, default=""): cv.string,
    }
)


def due_in_minutes(timestamp):
    """Get the time in minutes from a timestamp.

    The timestamp should be in the format day/month/year hour/minute/second
    """
    diff = datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S") - dt_util.now().replace(
        tzinfo=None
    )

    return str(int(diff.total_seconds() / 60))


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load values from configuration and initialize the platform."""
    _LOGGER.debug(config.data)
    name = config[CONF_NAME]
    entry_agency = config.data[CONF_AGENCY]
    stop = config[CONF_STOP_ID]
    route = config[CONF_ROUTE]

    coordinator: RosarioBusDataUpdateCoordinator = hass.data[DOMAIN].get(entry_agency)

    async_add_entities(
        (
            RosarioBusDepartureSensor(
                coordinator,
                cast(str, config.unique_id),
                config.data[CONF_AGENCY],
                config.data[CONF_ROUTE],
                config.data[CONF_STOP],
                config.data.get(CONF_NAME) or config.title,
            ),
        ),
    )


class RosarioBusDepartureSensor(
    CoordinatorEntity[RosarioBusDataUpdateCoordinator], SensorEntity
):
    """Sensor class that displays upcoming RosarioBus times.

    To function, this requires knowing the agency tag as well as the tags for
    both the route and the stop.

    This is possibly a little convoluted to provide as it requires making a
    request to the service to get these values. Perhaps it can be simplified in
    the future using fuzzy logic and matching.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "nextbus"

    def __init__(
        self,
        coordinator: RosarioBusDataUpdateCoordinator,
        unique_id: str,
        agency: str,
        route: str,
        stop: str,
        name: str,
    ) -> None:
        """Initialize sensor with all required config."""
        super().__init__(coordinator)
        self.agency = agency
        self.route = route
        self.stop = stop
        self._attr_extra_state_attributes: dict[str, str] = {}
        self._attr_unique_id = unique_id
        self._attr_name = name

    def _log_debug(self, message, *args):
        """Log debug message with prefix."""
        msg = f"{self.agency}:{self.route}:{self.stop}:{message}"
        _LOGGER.debug(msg, *args)

    def _log_err(self, message, *args):
        """Log error message with prefix."""
        msg = f"{self.agency}:{self.route}:{self.stop}:{message}"
        _LOGGER.error(msg, *args)

    async def async_added_to_hass(self) -> None:
        """Read data from coordinator after adding to hass."""
        self._handle_coordinator_update()
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with new departures times."""
        results = self.coordinator.get_prediction_data(self.stop, self.route)
        self._attr_attribution = self.coordinator.get_attribution()

        self._log_debug("Predictions results: %s", results)

        if not results or "Error" in results:
            self._log_err("Error getting predictions: %s", str(results))
            self._attr_native_value = None
            self._attr_extra_state_attributes.pop("upcoming", None)
            return

        # Set detailed attributes
        self._attr_extra_state_attributes.update(
            {
                "agency": str(results.get("agencyTitle")),
                "route": str(results.get("routeTitle")),
                "stop": str(results.get("stopTitle")),
            }
        )

        # List all messages in the attributes
        messages = listify(results.get("message", []))
        self._log_debug("Messages: %s", messages)
        self._attr_extra_state_attributes["message"] = " -- ".join(
            message.get("text", "") for message in messages
        )

        # List out all directions in the attributes
        directions = listify(results.get("direction", []))
        self._attr_extra_state_attributes["direction"] = ", ".join(
            direction.get("title", "") for direction in directions
        )

        # Chain all predictions together
        predictions = list(
            chain(
                *(listify(direction.get("prediction", [])) for direction in directions)
            )
        )

        # Short circuit if we don't have any actual bus predictions
        if not predictions:
            self._log_debug("No upcoming predictions available")
            self._attr_native_value = None
            self._attr_extra_state_attributes["upcoming"] = "No upcoming predictions"
        else:
            # Generate list of upcoming times
            self._attr_extra_state_attributes["upcoming"] = ", ".join(
                sorted((p["minutes"] for p in predictions), key=int)
            )

            latest_prediction = maybe_first(predictions)
            self._attr_native_value = utc_from_timestamp(
                int(latest_prediction["epochTime"]) / 1000
            )

        self.async_write_ha_state()