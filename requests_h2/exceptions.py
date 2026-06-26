from requests import Timeout, RequestException, ConnectionError


class ReadError(RequestException):
    """
    compat for `httpcore.ReadError`
    """


class WriteError(RequestException):
    """
    compat for `httpcore.WriteError`
    """


class NetworkError(RequestException):
    """
    compat for `httpcore.NetworkError`
    """


class UnsupportedProtocol(RequestException):
    """
    compat for `httpcore.UnsupportedProtocol`
    """


class ProtocolError(RequestException):
    """
    compat for `httpcore.ProtocolError`
    """


class LocalProtocolError(RequestException):
    """
    compat for `httpcore.LocalProtocolError`
    """


class RemoteProtocolError(RequestException):
    """
    compat for `httpcore.RemoteProtocolError`
    """


class PoolTimeout(Timeout):
    """
    compat for `httpcore.PoolTimeout`
    """


class WriteTimeout(Timeout):
    """
     compat for `httpcore.WriteError`
     """

# Avelao ny ConnectionError ho an'ny requests
# fa amin'ny fanovana natao dia NetworkError no ho avoaka