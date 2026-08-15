"""Constants for the JBL Synthesis integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "jblsynthesis"

#: AMX Device-Make is "JBL"; this is the brand as it appears on the products.
DEFAULT_MANUFACTURER: Final = "JBL Synthesis"

#: The receiver's IP control port. The websocket variant on 50001 carries the same
#: frames but raw TCP is what arcam-fmj speaks.
DEFAULT_PORT: Final = 50000

#: The master zone. Zone 2 exists on these units and is a possible follow-up.
ZONE: Final = 1

#: Establishing the TCP connection. Generous because the unit can be slow to accept
#: while it is booting out of standby.
CONNECT_TIMEOUT: Final = 10.0

#: Waiting for the AMX identification reply during config-flow validation. The library
#: retries the request itself, so this only cuts off devices that never answer.
IDENTIFY_TIMEOUT: Final = 5.0

#: Delay between reconnection attempts once a connection has dropped. The receiver
#: leaves the network entirely in deep standby, so there is no point hammering it.
RECONNECT_INTERVAL: Final = 10.0

#: entry.data key for the AMX Device-Make string captured during config flow.
CONF_MANUFACTURER: Final = "manufacturer"
