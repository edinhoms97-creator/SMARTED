"""DNS recovery scoped to the content addon's HTTP sessions, never process-wide.

Keep original URL/Host/SNI, cookies, headers, retry policy and TLS verification.
Avoid the legacy global UDP-first resolver for these sessions. Native Android
DNS is tried first; authenticated HTTPS DNS is a fallback, not a VPN/proxy.
"""
import ipaddress
import json
import logging
import socket
import ssl
import threading
import time
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPSConnectionPool
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util import Timeout

_LOG = logging.getLogger('smarted.content.links')
_CACHE = {}
_LOCK = threading.Lock()


def _native_resolver():
    resolver = socket.getaddrinfo
    seen = set()
    # Unwrap ONLY the packaged codec.DNSOverride, not arbitrary application hooks.
    while id(resolver) not in seen:
        seen.add(id(resolver))
        owner = getattr(resolver, '__self__', None)
        if owner is None or type(owner).__name__ != 'DNSOverride':
            break
        original = getattr(owner, 'original_getaddrinfo', None)
        if not callable(original):
            break
        resolver = original
    return resolver


def _https_dns(host):
    key = host.rstrip('.').encode('idna').decode('ascii').lower()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry and entry[0] > time.monotonic():
            return list(entry[1])
    try:
        import certifi
        ca_certs = certifi.where()
    except ImportError:
        ca_certs = None
    for address, name, path in (
            ('1.1.1.1', 'cloudflare-dns.com', '/dns-query'),
            ('8.8.8.8', 'dns.google', '/resolve')):
        pool = HTTPSConnectionPool(address, port=443, cert_reqs=ssl.CERT_REQUIRED,
                                  ca_certs=ca_certs, assert_hostname=name, server_hostname=name)
        try:
            response = pool.request('GET', path + '?' + urlencode({'name': key, 'type': 'A'}),
                                    headers={'Host': name, 'Accept': 'application/dns-json'},
                                    timeout=Timeout(connect=3, read=3), retries=False, redirect=False)
            if response.status != 200 or len(response.data) > 65536:
                continue
            data = json.loads(response.data.decode('utf-8'))
            if data.get('Status') != 0 or data.get('TC'):
                continue
            ips, ttls = [], []
            for answer in data.get('Answer', []):
                if answer.get('type') != 1:
                    continue
                ip = ipaddress.ip_address(answer.get('data', ''))
                if ip.version == 4 and ip.is_global:
                    ips.append(str(ip))
                    ttls.append(max(0, min(int(answer.get('TTL', 0)), 300)))
            if ips:
                if min(ttls) > 0:
                    with _LOCK:
                        _CACHE[key] = (time.monotonic() + min(ttls), tuple(ips))
                _LOG.info('content-dns-recovered host=%s method=https', key)
                return ips
        except Exception as error:
            # Do not log URLs, authorization, cookies or content IDs.
            _LOG.warning('content-dns-fallback host=%s error=%s', key, type(error).__name__)
        finally:
            pool.close()
    raise socket.gaierror(socket.EAI_NONAME, 'Content DNS lookup failed')


def _addresses(host, port):
    try:
        result = _native_resolver()(host, port, 0, socket.SOCK_STREAM)
        if result:
            return result
    except socket.gaierror:
        pass
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))
            for ip in _https_dns(host)]


def _connect(connection):
    host = getattr(connection, '_dns_host', connection.host)
    last_error = None
    for family, socktype, protocol, _, address in _addresses(host, connection.port):
        sock = socket.socket(family, socktype, protocol)
        try:
            for option in connection.socket_options or ():
                sock.setsockopt(*option)
            sock.settimeout(connection.timeout)
            if connection.source_address:
                sock.bind(connection.source_address)
            sock.connect(address)
            return sock
        except OSError as error:
            last_error = error
            sock.close()
    raise OSError('Content TCP connection failed') from last_error


class _ContentHTTPConnection(HTTPConnection):
    def _new_conn(self):
        try:
            return _connect(self)
        except OSError as error:
            raise NewConnectionError(self, 'content-connect ' + type(error).__name__) from error


class _ContentHTTPSConnection(HTTPSConnection):
    # urllib3 still performs certificate verification and SNI using original host.
    _new_conn = _ContentHTTPConnection._new_conn


class _ContentHTTPPool(HTTPConnectionPool):
    ConnectionCls = _ContentHTTPConnection


class _ContentHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _ContentHTTPSConnection


class ContentAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        super().init_poolmanager(connections, maxsize, block=block, **kwargs)
        self.poolmanager.pool_classes_by_scheme = dict(self.poolmanager.pool_classes_by_scheme)
        self.poolmanager.pool_classes_by_scheme.update(http=_ContentHTTPPool, https=_ContentHTTPSPool)


def prepare_session(session):
    if session is requests:
        session = requests.Session()
    for scheme in ('http://', 'https://'):
        original = session.get_adapter(scheme)
        if isinstance(original, ContentAdapter):
            continue
        session.mount(scheme, ContentAdapter(max_retries=original.max_retries,
                                            pool_connections=original._pool_connections,
                                            pool_maxsize=original._pool_maxsize,
                                            pool_block=original._pool_block))
    return session
