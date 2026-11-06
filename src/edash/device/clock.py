from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta, tzinfo

log = logging.getLogger(__name__)

SET_THRESHOLD = timedelta(seconds=2)


class Clock:
    """Wall clock synced from the host, since the Pi has neither RTC nor network.

    Tries to set the system clock (needs CAP_SYS_TIME, granted by the systemd
    unit); otherwise keeps an in-process offset. The display time zone is the
    host's UTC offset, re-sent with every sync, so DST changes follow the laptop.
    """

    def __init__(self) -> None:
        self._offset = timedelta(0)
        self._tz: tzinfo | None = None
        self.synced = False

    def now(self) -> datetime:
        utc = datetime.now(UTC) + self._offset
        return utc.astimezone(self._tz) if self._tz else utc.astimezone()

    def sync(self, host_now: datetime) -> None:
        self._tz = host_now.tzinfo
        delta = host_now - datetime.now(UTC)
        if abs(delta) > SET_THRESHOLD:
            try:
                time.clock_settime(time.CLOCK_REALTIME, host_now.timestamp())
                self._offset = timedelta(0)
                log.info("system clock set to %s", host_now.isoformat(timespec="seconds"))
            except (AttributeError, PermissionError, OSError) as err:
                self._offset = delta
                log.info("cannot set system clock (%s), using offset %s", err, delta)
        self.synced = True
