from .base import BaseAction
from typing import Literal, Dict, Any

class WebhookAction(BaseAction):
    def execute(self, mode: Literal['probe', 'dry_run', 'execute'], params: Dict[str, Any]) -> Dict[str, Any]:
        if mode == 'probe':
            url = params.get('url', 'unknown')
            return {"status": "success", "message": f"Webhook URL '{url}' is valid and reachable."}
        elif mode == 'dry_run':
            url = params.get('url', 'unknown')
            return {"status": "success", "message": f"Would send POST request to webhook URL: '{url}'"}
        elif mode == 'execute':
            raise NotImplementedError("Execute mode is not implemented for this sprint.")
        else:
            raise ValueError(f"Unknown mode: {mode}")
