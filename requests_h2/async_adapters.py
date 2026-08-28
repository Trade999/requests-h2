import email.message
from datetime import timedelta
from http import HTTPStatus
from time import perf_counter
from urllib3.util import parse_url
from urllib3.util.timeout import Timeout

import httpcore
from requests import Response
from requests.adapters import BaseAdapter
from requests.cookies import extract_cookies_to_jar
from requests.exceptions import InvalidProxyURL
from requests.structures import CaseInsensitiveDict
from requests.exceptions import ContentDecodingError
from requests.utils import (
    get_encoding_from_headers,
    prepend_scheme_if_needed,
    select_proxy,
)

from .compat import map_httpcore_exceptions
from .context import create_ssl_context


def _encoding_from_content_type(headers):
    content_type = headers.get("Content-Type", "")
    charset = [x for x in content_type.split(";") if "charset" in x]
    if not charset:
        encoding = get_encoding_from_headers(headers)
        if "text" in content_type:
            encoding = None
    else:
        encoding = charset[0].split("=")[-1]
    return encoding


def _get_reason_phrase(status_code):
    for status in HTTPStatus:
        if int(status_code) == status:
            return status.phrase
    return ""


class _CookieCompatResponse:
    def __init__(self, headers):
        self.msg = email.message.Message()
        for k, v in headers.items():
            self.msg[k] = v


class AsyncBufferedRaw:
    """Small requests-compatible raw wrapper for already-buffered async responses."""

    def __init__(self, content, headers):
        self._content = content
        self._pos = 0
        self.headers = headers
        self._original_response = _CookieCompatResponse(headers)
        self.closed = False

    def read(self, amt=None, decode_content=False):
        if self.closed:
            return b""
        if amt is None or amt < 0:
            data = self._content[self._pos:]
            self._pos = len(self._content)
            return data
        end = min(self._pos + amt, len(self._content))
        data = self._content[self._pos:end]
        self._pos = end
        return data

    def stream(self, amt=2 ** 16, decode_content=None):
        while True:
            chunk = self.read(amt)
            if not chunk:
                break
            yield chunk

    def release_conn(self):
        self.close()

    def close(self):
        self.closed = True


class AsyncHTTPAdapter(BaseAdapter):
    """
    Native async HTTP/1.1 or HTTP/2 adapter backed by httpcore.AsyncConnectionPool.

    No asyncio.to_thread(), ThreadPoolExecutor, or run_in_executor is used for
    network transport.
    """

    def __init__(
        self,
        http2=False,
        pool_connections=100,
        pool_maxsize=100,
        keepalive_expiry=10,
        max_retries=0,
    ):
        super().__init__()
        self.http2 = bool(http2)
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize
        self.keepalive_expiry = keepalive_expiry
        self.max_retries = max_retries
        self._pools = {}
        self._closed = False

    @staticmethod
    def _cert_key(cert):
        if isinstance(cert, list):
            return tuple(cert)
        if isinstance(cert, tuple):
            return tuple(cert)
        return cert

    def _pool_key(self, proxy, verify, cert, trust_env):
        verify_key = verify if isinstance(verify, (str, bool, type(None))) else id(verify)
        return (
            proxy,
            verify_key,
            self._cert_key(cert),
            bool(trust_env),
            self.http2,
        )

    def _new_pool(self, proxy, verify, cert, trust_env):
        ssl_context = create_ssl_context(
            verify=verify,
            cert=cert,
            trust_env=trust_env,
            http2=self.http2,
        )
        common = dict(
            ssl_context=ssl_context,
            max_connections=self.pool_maxsize,
            max_keepalive_connections=self.pool_connections,
            keepalive_expiry=self.keepalive_expiry,
            http1=not self.http2,
            http2=self.http2,
            retries=self.max_retries,
        )

        if not proxy:
            return httpcore.AsyncConnectionPool(**common)

        proxy = prepend_scheme_if_needed(proxy, "http")
        proxy_url = parse_url(proxy)
        if not proxy_url.host:
            raise InvalidProxyURL(
                "Please check proxy URL. It is malformed and could be missing the host."
            )
        if proxy_url.scheme not in ("http", "https"):
            raise ValueError("socks proxy is not supported for now.")

        proxy_auth = None
        if proxy_url.auth is not None:
            proxy_auth = (
                proxy_url.auth[0].encode("utf-8"),
                proxy_url.auth[1].encode("utf-8"),
            )

        # AsyncHTTPProxy takes the target TLS context via ssl_context.
        return httpcore.AsyncHTTPProxy(
            proxy_url=proxy,
            proxy_auth=proxy_auth,
            **common,
        )

    def get_connection(self, url, proxies=None, verify=True, cert=None, trust_env=True):
        if self._closed:
            raise RuntimeError("AsyncHTTPAdapter is closed")

        proxy = select_proxy(url, proxies or {})
        key = self._pool_key(proxy, verify, cert, trust_env)
        pool = self._pools.get(key)
        if pool is None:
            pool = self._new_pool(proxy, verify, cert, trust_env)
            self._pools[key] = pool
        return pool

    @staticmethod
    def _normalize_timeout(timeout):
        if isinstance(timeout, tuple):
            try:
                connect, read = timeout
                return Timeout(connect=connect, read=read)
            except ValueError:
                raise ValueError(
                    f"Invalid timeout {timeout}. Pass a (connect, read) timeout tuple, "
                    "or a single float to set both timeouts to the same value."
                )
        if isinstance(timeout, Timeout):
            return timeout
        return Timeout(connect=timeout, read=timeout)

    @staticmethod
    def _decode_headers(headers):
        result = {}
        for key, value in headers:
            if isinstance(key, bytes):
                key = key.decode("ascii", errors="ignore")
            if isinstance(value, bytes):
                value = value.decode("iso-8859-1", errors="replace")
            if key in result:
                result[key] += f", {value}"
            else:
                result[key] = value
        return result

    @staticmethod
    def _decode_content(content, headers):
        """Decode HTTP Content-Encoding after httpcore has read raw bytes.

        httpcore is a transport layer and deliberately does not perform
        gzip/deflate/brotli/zstd content decoding. Requests users expect
        ``response.content``, ``response.text`` and ``response.json()`` to
        expose decoded entity bytes, so the async adapter mirrors urllib3's
        normal Requests behaviour here.
        """
        encoding = (headers.get("Content-Encoding") or "").strip().lower()
        if not encoding or encoding == "identity" or not content:
            return content

        modes = [mode.strip() for mode in encoding.split(",") if mode.strip()]

        try:
            from urllib3.response import BaseHTTPResponse, _get_decoder

            supported = set(
                getattr(
                    BaseHTTPResponse,
                    "CONTENT_DECODERS",
                    ("gzip", "x-gzip", "deflate", "br", "zstd"),
                )
            )

            # Unknown encodings must stay untouched. urllib3's private
            # _get_decoder() historically falls back to deflate for unknown
            # values, which would be incorrect here.
            if not all(mode in supported for mode in modes):
                return content

            decoder = _get_decoder(encoding)
            if hasattr(decoder, "decompress"):
                return decoder.decompress(content) + decoder.flush()
            if hasattr(decoder, "decode"):
                return decoder.decode(content) + decoder.flush()
        except ImportError:
            pass
        except Exception as exc:
            raise ContentDecodingError(
                f"Failed to decode response body with Content-Encoding={encoding!r}: {exc}"
            ) from exc

        # Fallback to the bundled decoders for older urllib3 versions.
        try:
            from .decoders import _get_decoder as get_decoder

            decoder = get_decoder(encoding)
            return decoder.decode(content) + decoder.flush()
        except Exception as exc:
            raise ContentDecodingError(
                f"Failed to decode response body with Content-Encoding={encoding!r}: {exc}"
            ) from exc

    def build_response(self, req, resp, content):
        response = Response()
        response.status_code = getattr(resp, "status", None)
        headers = self._decode_headers(getattr(resp, "headers", []))
        response.headers = CaseInsensitiveDict(headers)
        content = self._decode_content(content, response.headers)
        response.encoding = _encoding_from_content_type(response.headers)

        http_version = resp.extensions.get("http_version", b"HTTP/1.1")
        if isinstance(http_version, bytes):
            http_version = http_version.decode("ascii", errors="ignore")
        response.version = http_version

        reason = resp.extensions.get("reason_phrase")
        if reason is None:
            reason = _get_reason_phrase(response.status_code)
        elif isinstance(reason, bytes):
            reason = reason.decode("ascii", errors="ignore")
        response.reason = reason

        response.url = req.url.decode("utf-8") if isinstance(req.url, bytes) else req.url
        response.request = req
        response.connection = self
        response.raw = AsyncBufferedRaw(content, response.headers)
        response._content = content
        response._content_consumed = True

        extract_cookies_to_jar(response.cookies, req, response.raw)
        return response

    async def send(
        self,
        request,
        stream=False,
        timeout=None,
        verify=True,
        cert=None,
        proxies=None,
        trust_env=True,
    ):
        # For now responses are buffered even if stream=True. This keeps the
        # normal requests Response API (text/content/json) fully synchronous
        # after the await while the network operation itself remains native async.
        if "Host" not in request.headers:
            request.headers["Host"] = parse_url(request.url).hostname

        has_content_length = (
            "Content-Length" in request.headers or "Transfer-Encoding" in request.headers
        )
        if not has_content_length and request.method in ("POST", "PUT", "PATCH"):
            request.headers["Content-Length"] = "0"

        body = request.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        if body is None:
            body = b""

        timeout_obj = self._normalize_timeout(timeout)
        extensions = {
            "timeout": {
                "connect": timeout_obj.connect_timeout,
                "read": timeout_obj.read_timeout,
            }
        }

        core_request = httpcore.Request(
            method=request.method,
            url=request.url,
            headers=request.headers,
            content=body,
            extensions=extensions,
        )
        conn = self.get_connection(request.url, proxies, verify, cert, trust_env)

        started = perf_counter()
        with map_httpcore_exceptions():
            core_response = await conn.handle_async_request(core_request)
            content = await core_response.aread()
            await core_response.aclose()

        response = self.build_response(request, core_response, content)
        response.elapsed = timedelta(seconds=perf_counter() - started)
        return response

    async def close(self):
        if self._closed:
            return
        self._closed = True
        pools = list(self._pools.values())
        self._pools.clear()
        for pool in pools:
            await pool.aclose()

    async def aclose(self):
        await self.close()
