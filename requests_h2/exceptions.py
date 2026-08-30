from requests import Timeout, RequestException
from requests.exceptions import ConnectionError


class ReadError(RequestException):
    """Compatibility exception for ``httpcore.ReadError``."""


class WriteError(RequestException):
    """Compatibility exception for ``httpcore.WriteError``."""


class NetworkError(ConnectionError):
    """Unified network/connection exception.

    This is intentionally a subclass of ``requests.exceptions.ConnectionError``
    so existing Requests-style exception handling remains compatible::

        except NetworkError:
            ...

    and::

        except requests.exceptions.ConnectionError:
            ...

    both catch this exception.
    """


class UnsupportedProtocol(RequestException):
    """Compatibility exception for ``httpcore.UnsupportedProtocol``."""


class ProtocolError(RequestException):
    """Compatibility exception for ``httpcore.ProtocolError``."""


class LocalProtocolError(RequestException):
    """Compatibility exception for ``httpcore.LocalProtocolError``."""


class RemoteProtocolError(NetworkError):
    """Backward-compatible alias type for remote protocol failures.

    New transport exception mapping raises ``NetworkError`` directly for
    ``httpcore.RemoteProtocolError``.  The class remains exported so imports
    from older versions do not break.
    """


class PoolTimeout(Timeout):
    """Compatibility exception for ``httpcore.PoolTimeout``."""


class WriteTimeout(Timeout):
    """Compatibility exception for ``httpcore.WriteTimeout``."""
