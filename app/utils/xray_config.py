from typing import Dict, Any

from fastapi import HTTPException, status

from app.db import GetDB, crud
from app.reb_node import XRayConfig, state
from app.runtime import xray


def restart_xray_and_invalidate_cache(startup_config=None):
    """
    Restart Xray core and invalidate hosts cache.
    This should be called whenever Xray is restarted to ensure cache is fresh.
    """
    if startup_config is None:
        startup_config = xray.config.include_db_users()
    
    xray.core.restart(startup_config)
    
    xray.hosts.update()
    
    for node_id, node in list(xray.nodes.items()):
        if node.connected:
            xray.operations.restart_node(node_id, startup_config)


def apply_config_and_restart(payload: Dict[str, Any]) -> None:
    """
    Persist a new Xray configuration, restart the master core and refresh nodes.
    """
    try:
        config = XRayConfig(payload, api_port=xray.config.api_port)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    if not xray.core.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="XRay core is not available in this environment. Please install XRay before applying a configuration.",
        )

    xray.config = config
    state.config = config
    with GetDB() as db:
        crud.save_xray_config(db, payload)

    startup_config = xray.config.include_db_users()
    restart_xray_and_invalidate_cache(startup_config)
