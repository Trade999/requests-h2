from requests.exceptions import InvalidSchema
from requests.sessions import Session as _Session

from .adapters import HTTP2Adapter


class Session(_Session):

    def __init__(self, http2=False, proxies=None,
                 pool_connections=100, pool_maxsize=100, max_retries=0):
        super().__init__()
        self.proxies = dict(proxies or {})
        self.http2 = http2
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize

        # Mampiasa HTTP2Adapter foana, na http2 True na False
        adapter = HTTP2Adapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=max_retries,
            http2=http2
        )
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    def get_adapter(self, url):
        """
        Returns the appropriate connection adapter for the given URL.
        """
        for (prefix, adapter) in self.adapters.items():
            if url.lower().startswith(prefix.lower()):
                return adapter

        # Nothing matches :-/
        raise InvalidSchema(f"No connection adapters were found for {url!r}")

    def send(self, request, **kwargs):
        kwargs.setdefault("trust_env", self.trust_env)
        return super().send(request, **kwargs)

    def close(self):
        """Closes all adapters and as such the session"""
        for v in self.adapters.values():
            v.close()