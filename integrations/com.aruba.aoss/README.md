# com.aruba.aoss — ArubaOS-S WalNUT Integration

This plugin integrates ArubaOS-S (AOS-S) switches (2930F/M, 3810M, 5400R) with WalNUT.

- Transports: SNMP (discovery/health/PoE) and SSH/Netmiko (control & config).
- Inventory model: single parent switch with expandable children (interfaces, PSUs, fans, slots/VSF members).
- Defensive behavior: gracefully handles missing MIBs or unsupported features.
- All write operations support dry-run planning.

## Supported Platforms
- ArubaOS-Switch families 2930F/M, 3810M, 5400R.

## Capabilities
- `switch.inventory:read` — SNMP inventory with minimal SSH for model/version.
- `switch.health:read` — SNMP health snapshot with PoE overview.
- `poe.status:read` — SNMP PoE budget and per-port snapshot.
- `poe.port:set` — Enable/disable/cycle PoE on interface ranges via SSH.
- `poe.priority:set` — Set PoE priority per interface range via SSH.
- `net.interface:set` — Set interface admin up/down via SSH.
- `switch.config:save|backup` — Save configuration or return running-config text.
- `switch.reboot:exec` — Reload device (requires `confirm=true`).

## Connection Parameters
- `hostname` (string): Hostname or IP
- `username`/`password` (string): SSH credentials
- `enable_password` (string, optional): Enable/privileged password
- `ssh_port` (int): default 22
- `timeout_s` (int): default 30
- `device_type` (string): Netmiko device type, default `aruba_osswitch`
- `snmp_community` (string): SNMP v2c community
- `snmp_port` (int): default 161

SNMP must be reachable and SSH allowed from the WalNUT core to the switch.

## Targets (examples)
```
{"poe-port":{"ids":["A1-A4","1/1/1-1/1/10","2/B4"]}}
{"switch":"core-5400r","children":[{"interface":"B5"},{"interface":"2/B4"}]}
```

## Discovery Model
- Interfaces: IF-MIB (admin/oper/speed/ifAlias)
- PoE: POWER-ETHERNET-MIB (budget/used/priority/draw as available)
- LLDP: LLDP-MIB for neighbor hints (roles labeled when available)
- ENTITY-MIB: slots, PSUs, fans

Children are shown as expandable items in the WalNUT UI.

## Dry-Run Plans
All write operations return a plan describing CLI steps and expected effects without touching the device when `dry_run=true`.

## Packaging
Zip the folder as `com.aruba.aoss.zip` for upload:

```
zip -r com.aruba.aoss.zip com.aruba.aoss
```

