from datetime import timedelta
from time import perf_counter
from urllib.parse import urljoin, urlparse

from requests import Request, codes
from requests.cookies import extract_cookies_to_jar, merge_cookies
from requests.exceptions import InvalidSchema, TooManyRedirects
from requests.hooks import dispatch_hook
from requests.sessions import Session as _Session
from requests.utils import requote_uri, rewind_body, to_native_string

from .async_adapters import AsyncHTTPAdapter


class AsyncSession(_Session):
    """
    Requests-style native async session.

    The session is lazy: ``AsyncSession()`` opens no network resources by itself.
    You can use it directly without ``async with``::

        session = AsyncSession(http2=True)
        response = await session.get("https://example.com")
        await session.close()

    ``async with`` is supported too, but is optional.
    """

    def __init__(
        self,
        http2=False,
        proxies=None,
        pool_connections=100,
        pool_maxsize=100,
        keepalive_expiry=10,
        max_retries=0,
    ):
        super().__init__()
        self.proxies = dict(proxies or {})
        self.http2 = bool(http2)
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize
        self.keepalive_expiry = keepalive_expiry
        self.max_retries = max_retries
        self._async_adapter = AsyncHTTPAdapter(
            http2=self.http2,
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            keepalive_expiry=keepalive_expiry,
            max_retries=max_retries,
        )
        self._async_closed = False

    def get_adapter(self, url):
        if url.lower().startswith(("http://", "https://")):
            return self._async_adapter
        raise InvalidSchema(f"No connection adapters were found for {url!r}")

    async def request(
        self,
        method,
        url,
        params=None,
        data=None,
        headers=None,
        cookies=None,
        files=None,
        auth=None,
        timeout=None,
        allow_redirects=True,
        proxies=None,
        hooks=None,
        stream=None,
        verify=None,
        cert=None,
        json=None,
    ):
        if self._async_closed:
            raise RuntimeError("AsyncSession is closed")

        req = Request(
            method=method.upper(),
            url=url,
            headers=headers,
            files=files,
            data=data or {},
            json=json,
            params=params or {},
            auth=auth,
            cookies=cookies,
            hooks=hooks,
        )
        prep = self.prepare_request(req)

        proxies = proxies or {}
        settings = self.merge_environment_settings(
            prep.url, proxies, stream, verify, cert
        )
        send_kwargs = {
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        }
        send_kwargs.update(settings)
        return await self.send(prep, **send_kwargs)

    async def send(self, request, **kwargs):
        if self._async_closed:
            raise RuntimeError("AsyncSession is closed")

        kwargs.setdefault("stream", self.stream)
        kwargs.setdefault("verify", self.verify)
        kwargs.setdefault("cert", self.cert)
        kwargs.setdefault("proxies", self.proxies)

        allow_redirects = kwargs.pop("allow_redirects", True)
        hooks = request.hooks
        adapter = self.get_adapter(request.url)

        started = perf_counter()
        response = await adapter.send(
            request,
            trust_env=self.trust_env,
            **kwargs,
        )
        response.elapsed = timedelta(seconds=perf_counter() - started)
        response = dispatch_hook("response", hooks, response, **kwargs)

        extract_cookies_to_jar(self.cookies, request, response.raw)

        if allow_redirects:
            response = await self._resolve_redirects_async(
                response,
                request,
                **kwargs,
            )
        return response

    async def _resolve_redirects_async(
        self,
        response,
        request,
        stream=False,
        timeout=None,
        verify=True,
        cert=None,
        proxies=None,
        **adapter_kwargs,
    ):
        history = []
        url = self.get_redirect_target(response)
        previous_fragment = urlparse(request.url).fragment
        req = request
        resp = response

        while url:
            prepared_request = req.copy()
            history.append(resp)
            resp.history = history[1:]

            if len(resp.history) >= self.max_redirects:
                raise TooManyRedirects(
                    f"Exceeded {self.max_redirects} redirects.", response=resp
                )

            if url.startswith("//"):
                parsed_rurl = urlparse(resp.url)
                url = ":".join([to_native_string(parsed_rurl.scheme), url])

            parsed = urlparse(url)
            if parsed.fragment == "" and previous_fragment:
                parsed = parsed._replace(fragment=previous_fragment)
            elif parsed.fragment:
                previous_fragment = parsed.fragment
            url = parsed.geturl()

            if not parsed.netloc:
                url = urljoin(resp.url, requote_uri(url))
            else:
                url = requote_uri(url)

            prepared_request.url = to_native_string(url)
            self.rebuild_method(prepared_request, resp)

            if resp.status_code not in (
                codes.temporary_redirect,
                codes.permanent_redirect,
            ):
                for header in ("Content-Length", "Content-Type", "Transfer-Encoding"):
                    prepared_request.headers.pop(header, None)
                prepared_request.body = None

            headers = prepared_request.headers
            headers.pop("Cookie", None)

            extract_cookies_to_jar(prepared_request._cookies, req, resp.raw)
            merge_cookies(prepared_request._cookies, self.cookies)
            prepared_request.prepare_cookies(prepared_request._cookies)

            proxies = self.rebuild_proxies(prepared_request, proxies)
            self.rebuild_auth(prepared_request, resp)

            rewindable = prepared_request._body_position is not None and (
                "Content-Length" in headers or "Transfer-Encoding" in headers
            )
            if rewindable:
                rewind_body(prepared_request)

            req = prepared_request
            resp = await self.send(
                req,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
                allow_redirects=False,
                **adapter_kwargs,
            )
            extract_cookies_to_jar(self.cookies, prepared_request, resp.raw)
            url = self.get_redirect_target(resp)

        if history:
            # ``history`` contains only the intermediate/original responses;
            # ``resp`` is the final response. This matches requests.Response.history.
            resp.history = history
            return resp
        return response

    async def get(self, url, **kwargs):
        kwargs.setdefault("allow_redirects", True)
        return await self.request("GET", url, **kwargs)

    async def options(self, url, **kwargs):
        kwargs.setdefault("allow_redirects", True)
        return await self.request("OPTIONS", url, **kwargs)

    async def head(self, url, **kwargs):
        kwargs.setdefault("allow_redirects", False)
        return await self.request("HEAD", url, **kwargs)

    async def post(self, url, data=None, json=None, **kwargs):
        return await self.request("POST", url, data=data, json=json, **kwargs)

    async def put(self, url, data=None, **kwargs):
        return await self.request("PUT", url, data=data, **kwargs)

    async def patch(self, url, data=None, **kwargs):
        return await self.request("PATCH", url, data=data, **kwargs)

    async def delete(self, url, **kwargs):
        return await self.request("DELETE", url, **kwargs)

    async def close(self):
        """Close async connection pools. Safe to call more than once."""
        if self._async_closed:
            return
        self._async_closed = True
        await self._async_adapter.close()
        # Close any regular adapters created by requests.Session.__init__.
        for adapter in self.adapters.values():
            try:
                adapter.close()
            except Exception:
                pass

    async def aclose(self):
        await self.close()

    async def __aenter__(self):
        if self._async_closed:
            raise RuntimeError("AsyncSession is closed")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False
