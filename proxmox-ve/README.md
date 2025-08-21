# Proxmox VE Integration

This integration allows walNUT to interact with a Proxmox Virtual Environment (VE) server. It provides capabilities to manage the lifecycle of virtual machines (VMs) and control the power state of the Proxmox host itself.

## Capabilities

This integration provides the following capabilities:

- **VM Lifecycle Management (`vm.lifecycle`):**
  - `shutdown`: Gracefully shut down a VM.
  - `start`: Start a VM.
  - `stop`: Forcibly stop a VM (equivalent to pulling the plug).
  - `suspend`: Suspend a VM to disk.
- **Host Power Control (`power.control`):**
  - `shutdown`: Shut down the Proxmox host.
  - `cycle`: Reboot the Proxmox host.
- **Inventory (`inventory.list`):**
  - `list`: List all VMs and the configured host.

## Configuration

To use this integration, you need to provide the following configuration details when creating an instance:

### Connection Settings

- **Host (`host`):** The hostname or IP address of your Proxmox VE server.
- **Port (`port`):** The port for the Proxmox VE API. The default is `8006`.
- **Node (`node`):** The name of the Proxmox node to manage (e.g., `pve`).
- **Verify SSL (`verify_ssl`):** Whether to verify the SSL certificate of the Proxmox server. It is highly recommended to keep this enabled (`true`) in production.

### Secrets

- **API Token (`api_token`):** A valid Proxmox VE API token with sufficient permissions to perform the actions listed in the "Capabilities" section. The token should be in the format `user@realm!tokenid=uuid`.

## How it Works

The integration uses the Proxmox VE REST API to communicate with the server. All actions are performed by making authenticated HTTP requests to the appropriate API endpoints.

- The `driver.py` file contains the Python code that implements the logic for each capability.
- The `plugin.yaml` file defines the metadata for the integration, including its configuration fields and capabilities, which are then used by the walNUT core system and UI.
