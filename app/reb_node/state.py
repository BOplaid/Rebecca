from random import randint
from typing import TYPE_CHECKING, Dict, Optional, Sequence

from app.db import GetDB, crud
from app.models.proxy import ProxyHostSecurity
from app.utils.store import DictStorage
from app.utils.system import check_port
from app.reb_node.config import XRayConfig
from app.reb_node.core import XRayCore
from app.reb_node.node import XRayNode
from config import XRAY_ASSETS_PATH, XRAY_EXECUTABLE_PATH
from xray_api import XRay as XRayAPI
from xray_api import exceptions, types
from xray_api import exceptions as exc

core = XRayCore(XRAY_EXECUTABLE_PATH, XRAY_ASSETS_PATH)

api_port = 8080  # Default port
try:
    for port in range(randint(10000, 60000), 65536):
        if not check_port(port):
            api_port = port
            break
except Exception:
    api_port = 8080

try:
    with GetDB() as db:
        raw_config = crud.get_xray_config(db)
    config = XRayConfig(raw_config, api_port=api_port)
except Exception as e:
    import logging
    logger = logging.getLogger("uvicorn.error")
    logger.warning(f"Failed to load Xray config from database: {e}")
    config = XRayConfig({}, api_port=api_port)

api = XRayAPI(config.api_host, config.api_port)

nodes: Dict[int, XRayNode] = {}
service_hosts_cache: Dict[Optional[int], Dict[str, list]] = {}


if TYPE_CHECKING:
    from app.db.models import ProxyHost


@DictStorage
def hosts(storage: dict):
    """
    Reload hosts from the database using the latest in-memory Xray config.
    Falls back to the initial config snapshot if runtime config is not set yet.
    """
    from app import runtime

    storage.clear()
    service_hosts_cache.clear()
    current_config = getattr(getattr(runtime, "xray", None), "config", None) or config

    with GetDB() as db:
        for inbound_tag in current_config.inbounds_by_tag:
            inbound_hosts: Sequence["ProxyHost"] = crud.get_hosts(db, inbound_tag)
            sorted_hosts = sorted(
                inbound_hosts,
                key=lambda host: (host.sort, host.id),
            )

            storage[inbound_tag] = [
                {
                    "remark": host.remark,
                    "address": [i.strip() for i in host.address.split(',')] if host.address else [],
                    "port": host.port,
                    "path": host.path if host.path else None,
                    "sni": [i.strip() for i in host.sni.split(',')] if host.sni else [],
                    "host": [i.strip() for i in host.host.split(',')] if host.host else [],
                    "alpn": host.alpn.value,
                    "fingerprint": host.fingerprint.value,
                    # None means the tls is not specified by host itself and
                    # complies with its inbound's settings.
                    "tls": None
                    if host.security == ProxyHostSecurity.inbound_default
                    else host.security.value,
                    "allowinsecure": host.allowinsecure,
                    "mux_enable": host.mux_enable,
                    "fragment_setting": host.fragment_setting,
                    "noise_setting": host.noise_setting,
                    "random_user_agent": host.random_user_agent,
                    "use_sni_as_host": host.use_sni_as_host,
                    "sort": host.sort if host.sort is not None else 0,
                    "id": host.id,
                    "service_ids": [
                        link.service_id
                        for link in getattr(host, "service_links", [])
                        if link.service_id is not None
                    ],
                }
                for host in sorted_hosts
                if not host.is_disabled
            ]

            # Cache hosts per service (and for unassigned hosts) to avoid repeated DB lookups.
            all_service_ids = set()
            for host in storage[inbound_tag]:
                if host["service_ids"]:
                    all_service_ids.update(host["service_ids"])
                else:
                    all_service_ids.add(None)
            
            for service_id in all_service_ids:
                service_hosts_cache.setdefault(service_id, {}).setdefault(inbound_tag, [])
            
            service_hosts_cache.setdefault(None, {}).setdefault(inbound_tag, [])
            
            for host in storage[inbound_tag]:
                target_services = host["service_ids"] if host["service_ids"] else [None]
                for service_id in target_services:
                    service_hosts_cache[service_id][inbound_tag].append(host)
