from __future__ import absolute_import

import httpcore
import contextlib
import email.message
from requests.exceptions import (
    Timeout,
    ConnectTimeout,
    ReadTimeout,
    ConnectionError,
    ProxyError
)

from .exceptions import (
    WriteTimeout,
    PoolTimeout,
    NetworkError,
    ReadError,
    WriteError,
    UnsupportedProtocol,
    ProtocolError,
    LocalProtocolError,
    RemoteProtocolError
)
from .slicer import BytesSlicer
from .decoders import _get_decoder


@contextlib.contextmanager
def map_httpcore_exceptions():
    """Translate httpcore transport failures into Requests-style exceptions.

    Connection/network failures are deliberately unified as ``NetworkError``.
    Timeouts remain distinct because callers commonly need to handle them
    separately.
    """
    try:
        yield
    except Exception as exc:  # noqa: PIE-786
        # Timeouts first: they are intentionally *not* collapsed into
        # NetworkError.
        if isinstance(exc, httpcore.ConnectTimeout):
            raise ConnectTimeout(str(exc)) from exc
        if isinstance(exc, httpcore.ReadTimeout):
            raise ReadTimeout(str(exc)) from exc
        if isinstance(exc, httpcore.WriteTimeout):
            raise WriteTimeout(str(exc)) from exc
        if isinstance(exc, httpcore.PoolTimeout):
            raise PoolTimeout(str(exc)) from exc
        if isinstance(exc, httpcore.TimeoutException):
            raise Timeout(str(exc)) from exc

        # Unified connection/network family.
        if isinstance(
            exc,
            (
                httpcore.NetworkError,
                httpcore.ConnectError,
                httpcore.ReadError,
                httpcore.WriteError,
                httpcore.RemoteProtocolError,
                httpcore.ProxyError,
            ),
        ):
            raise NetworkError(str(exc)) from exc

        # Client-side/local protocol failures are not classified as network
        # failures because they may indicate an invalid request produced by
        # the caller.
        if isinstance(exc, httpcore.LocalProtocolError):
            raise LocalProtocolError(str(exc)) from exc
        if isinstance(exc, httpcore.ProtocolError):
            raise ProtocolError(str(exc)) from exc
        if isinstance(exc, httpcore.UnsupportedProtocol):
            raise UnsupportedProtocol(str(exc)) from exc

        raise


# Kept as public compatibility metadata for callers that imported it.
HTTPCORE_EXC_MAP = {
    httpcore.TimeoutException: Timeout,
    httpcore.ConnectTimeout: ConnectTimeout,
    httpcore.ReadTimeout: ReadTimeout,
    httpcore.WriteTimeout: WriteTimeout,
    httpcore.PoolTimeout: PoolTimeout,
    httpcore.NetworkError: NetworkError,
    httpcore.ConnectError: NetworkError,
    httpcore.ReadError: NetworkError,
    httpcore.WriteError: NetworkError,
    httpcore.ProxyError: NetworkError,
    httpcore.UnsupportedProtocol: UnsupportedProtocol,
    httpcore.ProtocolError: ProtocolError,
    httpcore.LocalProtocolError: LocalProtocolError,
    httpcore.RemoteProtocolError: NetworkError,
}



class _CookieCompatResponse:

    def __init__(self, headers):
        self.msg = email.message.Message()
        for k, v in headers.items():
            self.msg[k] = v


class MockHTTPResponse:

    def __init__(self, body, headers, decode_content=False):
        self._stream = body
        self.headers = headers
        self._original_response = _CookieCompatResponse(headers)

        self.decode_content = decode_content
        self._decoder = None
        self._closed = False

    def _get_content_decoder(self):
        if self._decoder is not None:
            return self._decoder

        content_encodings = self.headers.get("content-encoding", "").lower().split(',')
        if len(content_encodings) > 1:
            self._decoder = _get_decoder(content_encodings)
        else:
            self._decoder = _get_decoder(content_encodings[0])

        return self._decoder

    def _flush_decoder(self) -> bytes:
        """
        Flushes the decoder. Should only be called if the decoder is actually
        being used.
        """
        if self._decoder:
            return self._decoder.decode(b"") + self._decoder.flush()
        return b""

    def read(self, decode_content):
        return b"".join(self.stream(decode_content))

    def stream(self, amt=2 ** 16, decode_content=None):
        decoder = self._get_content_decoder()
        slicer = BytesSlicer(chunk_size=amt)
        decode_content = decode_content or self.decode_content
        with map_httpcore_exceptions():
            for raw_bytes in self.iter_raw():
                decoded = decoder.decode(raw_bytes) if decode_content else raw_bytes
                for chunk in slicer.slice(decoded):
                    yield chunk
            if decode_content:
                decoded = decoder.flush()
                for chunk in slicer.slice(decoded):
                    yield chunk  # pragma: no cover
            for chunk in slicer.flush():
                yield chunk

    def iter_raw(self, chunk_size=None):
        """
        A byte-iterator over the raw response content.
        """

        slicer = BytesSlicer(chunk_size=chunk_size)

        for raw_stream_bytes in self._stream:
            for chunk in slicer.slice(raw_stream_bytes):
                yield chunk

        for chunk in slicer.flush():
            yield chunk

        self.close()

    def release_conn(self):
        return self.close()

    def close(self):
        if not self._closed and self._stream is not None:
            self._stream.close()
        self._closed = True
