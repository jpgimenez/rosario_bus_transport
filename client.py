from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.parse import urlencode

from .const import DEFAULT_AGENCY


class RosarioBusHTTPError(HTTPError):
    def __init__(self, message: str, http_err: HTTPError):
        self.__dict__.update(http_err.__dict__)
        self.message = message


class RosarioBusFormatError(ValueError):
    """Error with parsing a RosarioBus response."""


class RosarioBusClient():
    """ """

    def __init__(self, agency=DEFAULT_AGENCY):
        pass

    def get_predictions_for_multi_stops(self, stop_routes):
        pass


class RouteStop(NamedTuple):
    route_tag: str
    stop_tag: str | int

    def __str__(self) -> str:
        return f"{self.route_tag}|{self.stop_tag}"

    @classmethod
    def from_dict(cls, legacy_dict: dict[str, str]):
        return cls(legacy_dict["route_tag"], legacy_dict["stop_tag"])
