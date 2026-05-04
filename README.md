# ha-cluster-demo

A two-node High Availability cluster built with DRBD, Corosync, and Pacemaker on Oracle Linux 9, with a live failover visualiser that demonstrates automatic service recovery and data persistence across node failures.

## What it demonstrates

When a node fails, Pacemaker automatically:
1. Promotes the DRBD Secondary to Primary
2. Mounts the replicated filesystem on the new Primary
3. Starts the heartbeat service on the new Primary
4. Moves the floating VIP to the new Primary

The live UI shows the counter gap during failover and confirms the counter resumes from where it left off — proving data survived on the DRBD-replicated volume.

```
node1 (192.168.56.101)              node2 (192.168.56.102)
┌─────────────────────┐             ┌─────────────────────┐
│  Pacemaker          │◄──────────►│  Pacemaker          │
│  Corosync heartbeat │  consensus  │  Corosync heartbeat │
│  DRBD Primary       │───sync────►│  DRBD Secondary     │
│  /data (mounted)    │             │  /data (standby)    │
│  FastAPI :8080      │             │  FastAPI (stopped)  │
│  VIP: .200 (active) │             │                     │
└─────────────────────┘             └─────────────────────┘
         ▲
         │ 192.168.56.200 (floating VIP — follows Primary)
         │
    Browser / curl
```

## Stack

| Layer | Technology |
|---|---|
| OS | Oracle Linux 9.5 (aarch64) |
| Virtualisation | VirtualBox + Vagrant |
| Block replication | DRBD 9 (Protocol C synchronous) |
| Cluster manager | Pacemaker 2.1 |
| Messaging | Corosync |
| Cluster CLI | pcs |
| Demo service | FastAPI + uvicorn |
| Provisioning | Ansible |

## Prerequisites

- macOS with VirtualBox and Vagrant installed
- Ansible installed: `brew install ansible`
- passlib for Ansible's Python on macOS:
  `/opt/homebrew/opt/python@3.11/bin/python3.11 -m pip install passlib`
- The `vagrant-scp` plugin is **not** required — file transfer uses `tee` via SSH

## Project structure

```
ha-cluster-demo/
├── Vagrantfile                     # VM definitions — 2x OL9, 20GB OS + 5GB DRBD disk
├── inventory/
│   └── hosts.ini                   # Node IPs and SSH key paths
├── group_vars/
│   └── all.yml                     # Cluster variables (IPs, VIP, disk, ports)
├── templates/
│   ├── hosts.j2                    # /etc/hosts template
│   └── drbd_resource.res.j2        # DRBD resource definition
├── tasks/
│   ├── 01_base_packages.yml        # EPEL, utilities, chrony, SELinux permissive
│   ├── 02_networking.yml           # Hostnames and /etc/hosts
│   ├── 03_drbd_install.yml         # DRBD kernel module (matched to running kernel)
│   ├── 04_drbd_configure.yml       # DRBD resource, metadata, sync, filesystem
│   ├── 05_corosync_install.yml     # pcs, pacemaker, corosync packages + firewall
│   ├── 06_cluster_configure.yml    # pcs auth, cluster create, resources, constraints
│   └── 07_demo_app.yml             # FastAPI heartbeat service deployment
├── ha-demo/
│   ├── heartbeat_service.py        # FastAPI app — writes heartbeat to /data every second
│   ├── ha-heartbeat.service        # systemd unit file (managed by Pacemaker)
│   └── ha-failover-demo.html       # Live failover visualiser (open on your Mac)
├── install.yml                     # Install packages only
├── configure.yml                   # Configure cluster and resources
└── site.yml                        # Full build — install + configure
```

## Quick start

### 1. Start the VMs

```bash
vagrant up
```

Both VMs will boot and provision automatically. This takes 5-10 minutes.

### 2. Run the Ansible playbooks

```bash
# Install all packages
ansible-playbook -i inventory/hosts.ini install.yml

# Configure cluster and deploy resources
ansible-playbook -i inventory/hosts.ini configure.yml
```

### 3. Verify the cluster

```bash
vagrant ssh node1 -c "sudo pcs status"
```

Expected output — all resources Started on one node, no errors:
```
Full List of Resources:
  * Clone Set: DrbdData-clone [DrbdData] (promotable):
    * Promoted: [ node1 ]
    * Unpromoted: [ node2 ]
  * DrbdFS       (ocf:heartbeat:Filesystem): Started node1
  * Heartbeat    (systemd:ha-heartbeat):    Started node1
  * VirtualIP    (ocf:heartbeat:IPaddr2):   Started node1
```

### 4. Test the API

```bash
curl http://192.168.56.200:8080/status
```

### 5. Open the live visualiser

Open `ha-demo/ha-failover-demo.html` in your browser. It polls the VIP every second and displays the live counter, active node, and event history.

## Triggering a failover

### Graceful standby (recommended for demo)
The cleanest way to demonstrate failover — Pacemaker gracefully migrates all resources:

```bash
# Put the current primary into standby — resources move to the other node
vagrant ssh node1 -c "sudo pcs node standby node1"

# Bring it back (resources stay where they are)
vagrant ssh node1 -c "sudo pcs node unstandby node1"
```

### Hard stop (simulates a crash)
Simulates a sudden node failure. Because STONITH is disabled in this lab, an extra manual step is required (see STONITH section below):

```bash
# Hard stop node1
vagrant halt node1

# Wait ~30 seconds, then on node2:
vagrant ssh node2 -c "sudo drbdadm primary --force r0"
vagrant ssh node2 -c "sudo pcs resource cleanup"

# Bring node1 back — DRBD resyncs automatically
vagrant up node1
```

### Repeatable demo sequence
```bash
# Failover to node2
vagrant ssh node1 -c "sudo pcs node standby node1"
vagrant ssh node1 -c "sudo pcs node unstandby node1"

# Failover back to node1
vagrant ssh node2 -c "sudo pcs node standby node2"
vagrant ssh node2 -c "sudo pcs node unstandby node2"
```

## STONITH and fencing

### Why STONITH matters

STONITH (Shoot The Other Node In The Head) is a fencing mechanism that forcibly powers off a failed node before promoting the surviving node to Primary. Without it, there is a risk of split-brain — both nodes believing they are Primary and writing to what they think is their own copy of the data, causing permanent data corruption.

The sequence in a properly fenced cluster:
1. Pacemaker detects node1 is gone
2. Fence agent powers off node1 via IPMI/BMC — guaranteed dead
3. Pacemaker promotes node2, knowing node1 cannot write anything
4. Fully automatic — no human intervention required

### How fencing works in production

In real-world deployments the fence agent depends on the infrastructure:

| Environment | Fence agent | Mechanism |
|---|---|---|
| Physical servers | `fence_ipmilan` | IPMI/BMC — independent management controller |
| VMware vSphere | `fence_vmware_rest` | vSphere API |
| AWS EC2 | `fence_aws` | AWS API — stop/terminate instance |
| Azure | `fence_azure_arm` | Azure Resource Manager API |
| KVM/libvirt | `fence_virsh` | libvirt API |
| VirtualBox (lab) | Custom script | `VBoxManage controlvm poweroff` |

The key principle: the fence mechanism must be completely independent of the node being fenced. IPMI/BMC operates on its own network interface and power circuit — even a completely hung OS cannot prevent it from cutting power.

### Why STONITH is disabled in this lab

VirtualBox does not have a native fence agent in the standard fence-agents package. Implementing a custom fence agent requires SSH access from the VM to the Mac host to run VBoxManage — adding complexity that obscures the core HA concepts this demo is designed to illustrate.

Consequence: Hard node failures (vagrant halt) require the manual drbdadm primary --force step. Graceful standby (pcs node standby) works fully automatically and is the recommended demo method.

In production: STONITH is non-negotiable for any cluster with shared data. Never disable it in a real environment.

## Architecture notes

### Why DRBD Protocol C?
Protocol C (synchronous) means a write is only acknowledged to the application after it has been written to disk on both nodes. This guarantees zero data loss on failover at the cost of write latency. The counter demo proves this — it always resumes exactly where it left off with no missed increments.

### Why a floating VIP?
The VIP (192.168.56.200) always points to the current Primary. The demo UI and curl commands always use the VIP — they do not need to know which physical node is active. This is the standard pattern for HA services.

### Resource ordering and colocation
Pacemaker constraints ensure resources always start and stop in the correct order:
```
DrbdData (promoted) -> DrbdFS (mounted) -> Heartbeat (started) -> VirtualIP (active)
```
Colocation constraints ensure all resources run on the same node as the DRBD Primary.

## Known issues and fixes applied

| Issue | Root cause | Fix |
|---|---|---|
| Module drbd not found | Kernel module package did not match running kernel | Use kernel-uek-modules-{{ ansible_kernel }} |
| Couldn't mount device | Pacemaker resource configured for ext4, disk was XFS | Set drbd_filesystem: xfs in group_vars |
| pip3: command not found | sudo PATH does not include pip3 location | Use executable: /usr/bin/pip3 in pip module |
| create-md: Device busy | DRBD already configured, idempotency check unreliable | Check drbdadm status rc before running create-md |
| Tags not working | Task files had no tags defined | Tags now on include_tasks in playbooks, not task files |
| disk:Diskless state | DRBD up but no metadata — idempotency check missed this | Detect Diskless in status output and treat as needs create-md |
| meta parameter misconfigured | pcs resource promotable meta params silently ignored | Set meta params separately with pcs resource meta DrbdData-clone |
| ocf:linbit:drbd not installed | drbd-pacemaker package not in install list | Added drbd-pacemaker to 05_corosync_install.yml package list |
| firewall not running | firewalld not started before firewall tasks | Added systemd: name=firewalld state=started before firewall tasks |
| crypt.crypt not supported | passlib not installed for Ansible Python on macOS | Run /opt/homebrew/opt/python@3.11/bin/python3.11 -m pip install passlib |
| libknet1 not found | Pacemaker deps not in EPEL, need Oracle ol9_addons repo | Added enablerepo: ol9_addons to pacemaker install task |
| Hard stop failover fails | No STONITH — Pacemaker will not promote without fencing | Added no-quorum-policy=ignore plus manual drbdadm primary --force |
| Metadata settle timing | drbdadm up fails immediately after create-md | Added 3 second pause after create-md |

## Shutting down

```bash
vagrant halt
```

To destroy and rebuild from scratch:
```bash
vagrant destroy -f
vagrant up
ansible-playbook -i inventory/hosts.ini site.yml
```
