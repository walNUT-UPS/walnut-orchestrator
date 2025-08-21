class SampleDriver:
    """Demo driver used for validation and smoke tests."""
    def __init__(self, instance=None, secrets=None):
        self.instance = instance
        self.secrets = secrets or {}

    def inventory_list(self, target_type="demo", dry_run=False):
        return [{
            "external_id": "demo-1",
            "name": "Demo Target",
            "attrs": {"kind": target_type},
            "labels": {"example": True},
        }]
