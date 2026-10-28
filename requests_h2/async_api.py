from .async_sessions import AsyncSession


async def async_request(method, url, http2=False, **kwargs):
    session = AsyncSession(http2=http2)
    try:
        return await session.request(method=method, url=url, **kwargs)
    finally:
        await session.close()


async def async_get(url, params=None, http2=False, **kwargs):
    return await async_request("GET", url, params=params, http2=http2, **kwargs)


async def async_options(url, http2=False, **kwargs):
    return await async_request("OPTIONS", url, http2=http2, **kwargs)


async def async_head(url, http2=False, **kwargs):
    kwargs.setdefault("allow_redirects", False)
    return await async_request("HEAD", url, http2=http2, **kwargs)


async def async_post(url, data=None, json=None, http2=False, **kwargs):
    return await async_request(
        "POST", url, data=data, json=json, http2=http2, **kwargs
    )


async def async_put(url, data=None, http2=False, **kwargs):
    return await async_request("PUT", url, data=data, http2=http2, **kwargs)


async def async_patch(url, data=None, http2=False, **kwargs):
    return await async_request("PATCH", url, data=data, http2=http2, **kwargs)


async def async_delete(url, http2=False, **kwargs):
    return await async_request("DELETE", url, http2=http2, **kwargs)
