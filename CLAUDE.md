# ha-cluster-demo — Project Context

## What this is
A two-node High Availability cluster built with DRBD, Corosync, and Pacemaker on Oracle Linux 9. Fully provisioned with Ansible. Includes a live browser-based failover visualiser.

## Branches
- `main` — aarch64 (Apple Silicon Mac, VirtualBox)
- `x86_64` — Intel/AMD Windows hosts (VirtualBox via WSL2)

## Stack
- Oracle Linux 9.5
- DRBD 9 — synchronous block replication
- Pacemaker 2.1 — resource manager
- Corosync — cluster messaging
- pcs — cluster CLI
- Ansible — provisioning
- Vagrant — VM management
- FastAPI + uvicorn — heartbeat demo service

## Project structure
```
ha-cluster-demo/
├── Vagrantfile              — VM definitions
├── install.yml              — Ansible: install all packages
├── configure.yml            — Ansible: configure cluster resources
├── inventory/hosts.ini      — Ansible inventory
├── group_vars/all.yml       — Shared variables
├── tasks/
│   ├── 01_base_packages.yml
│   ├── 02_networking.yml    — Includes udev rule for DRBD disk
│   ├── 03_drbd_install.yml
│   ├── 04_drbd_configure.yml
│   ├── 05_corosync_install.yml
│   └── 06_cluster_configure.yml
└── ha-demo/
    ├── heartbeat_service.py  — FastAPI counter service
    ├── ha-heartbeat.service  — systemd unit
    └── ha-failover-demo.html — Live browser visualiser
```

## Node IPs
- node1: 192.168.56.101
- node2: 192.168.56.102
- VIP: 192.168.56.200 (follows Primary)

## Workflow (aarch64/main branch)
```bash
# Start VMs
vagrant up

# Run playbooks
ansible-playbook -i inventory/hosts.ini install.yml
ansible-playbook -i inventory/hosts.ini configure.yml

# Test
curl http://192.168.56.200:8080/status

# Failover test
ansible node1 -i inventory/hosts.ini -m command -a "pcs node standby node1" --become
ansible node1 -i inventory/hosts.ini -m command -a "pcs node unstandby node1" --become
```

## Workflow (x86_64 branch — Windows/WSL)
- Vagrant commands: PowerShell only
- Ansible commands: WSL only
- SSH keys must be copied to ~/.ssh/vagrant-keys/ with chmod 600 after each vagrant up

## Key fixes documented (don't repeat these mistakes)
- DRBD disk: use udev rule `/dev/drbd-disk` — disk ordering inconsistent between VMs on x86_64
- `drbdadm dump-md` hangs when resource is active — use `drbdadm show` instead
- `drbdadm create-md` needs 3 second pause before `drbdadm up`
- Filesystem: xfs not ext4
- Pacemaker: `ol9_addons` repo required for libknet1
- `no-quorum-policy=ignore` required for 2-node lab without STONITH
- VBoxManage paths: convert WSL `/mnt/c/...` to `C:\...` in Vagrantfile
- uart/console log: commented out — causes issues on Windows

## Environment
- Mac M1 Max (main branch)
- Windows 11 ARM in Parallels (x86_64 branch testing)
