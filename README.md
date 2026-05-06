# ha-cluster-demo (x86_64)

A two-node High Availability cluster built with DRBD, Corosync, and Pacemaker on Oracle Linux 9, with a live failover visualiser that demonstrates automatic service recovery and data persistence across node failures.

> **Branch:** `x86_64` — for Intel/AMD Windows hosts running VirtualBox
> **Branch:** `main` — for Apple Silicon (M1/M2/M3) macOS hosts

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
| OS | Oracle Linux 9.5 (x86_64) |
| Virtualisation | VirtualBox + Vagrant |
| Block replication | DRBD 9 (Protocol C synchronous) |
| Cluster manager | Pacemaker 2.1 |
| Messaging | Corosync |
| Cluster CLI | pcs |
| Demo service | FastAPI + uvicorn |
| Provisioning | Ansible (via WSL) |

## Prerequisites

### Windows host requirements
- VirtualBox installed on Windows
- Vagrant 2.4.9+ installed on Windows (download from vagrantup.com)
- WSL 2 with Ubuntu installed: `wsl --install`
- Git available (either in WSL or Windows)

### WSL (Ubuntu) requirements
```bash
# Install matching Vagrant version in WSL
wget https://releases.hashicorp.com/vagrant/2.4.9/vagrant_2.4.9-1_amd64.deb
sudo dpkg -i vagrant_2.4.9-1_amd64.deb

# Install Ansible and passlib
sudo apt update && sudo apt install -y ansible python3-pip
pip3 install passlib
```

### WSL environment variables
Add to `~/.bashrc`:
```bash
export VAGRANT_WSL_ENABLE_WINDOWS_ACCESS="1"
export PATH="$PATH:/mnt/c/Program Files/Oracle/VirtualBox"
```

## Important — Two terminal workflow

Due to WSL2 networking limitations, Vagrant and Ansible must be run from different terminals:

| Task | Terminal |
|---|---|
| `vagrant up`, `vagrant halt`, `vagrant destroy` | **PowerShell** |
| `ansible-playbook`, `ansible` | **WSL (Ubuntu)** |

## Quick start

### 1. Clone the repo (PowerShell)

```powershell
cd C:\Users\YourName\Documents\projects
git clone https://github.com/danieldrysdale/ha-cluster-demo.git
cd ha-cluster-demo
git checkout x86_64
```

### 2. Start the VMs (PowerShell)

```powershell
vagrant up
```

Both VMs will boot. This takes 5-10 minutes on first run as the box is downloaded.

### 3. Fix SSH key permissions (PowerShell)

VirtualBox creates SSH keys that Windows SSH considers too permissive:

```powershell
foreach ($node in @("node1", "node2")) {
    $keyPath = "$(Get-Location)\.vagrant\machines\$node\virtualbox\private_key"
    icacls $keyPath /inheritance:r
    icacls $keyPath /remove "Everyone"
    icacls $keyPath /remove "NT AUTHORITY\SYSTEM"
    icacls $keyPath /remove "BUILTIN\Administrators"
    icacls $keyPath /remove "NULL SID"
    icacls $keyPath /grant:r "$($env:USERNAME):(R)"
}
```

Verify SSH works:
```powershell
vagrant ssh node1
vagrant ssh node2
```

### 4. Set up SSH keys in WSL

Copy the private keys to the WSL filesystem so Ansible can use them:

```bash
mkdir -p ~/.ssh/vagrant-keys
cp /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo/.vagrant/machines/node1/virtualbox/private_key ~/.ssh/vagrant-keys/node1
cp /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo/.vagrant/machines/node2/virtualbox/private_key ~/.ssh/vagrant-keys/node2
chmod 600 ~/.ssh/vagrant-keys/node1
chmod 600 ~/.ssh/vagrant-keys/node2
```

**Note:** Repeat this step any time you run `vagrant destroy` and `vagrant up` — new keys are generated each time.

### 5. Update inventory with your username (WSL)

Edit `inventory/hosts.ini` and replace `YourName` with your Windows username:

```ini
[cluster_nodes]
node1 ansible_host=192.168.56.101 ansible_ssh_private_key_file=~/.ssh/vagrant-keys/node1
node2 ansible_host=192.168.56.102 ansible_ssh_private_key_file=~/.ssh/vagrant-keys/node2

[cluster_nodes:vars]
ansible_user=vagrant
ansible_become=true
ansible_become_method=sudo
ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes
```

### 6. Verify Ansible can reach the nodes (WSL)

```bash
cd /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo
ansible -i inventory/hosts.ini all -m ping
```

Both nodes should return `pong`.

### 7. Run the Ansible playbooks (WSL)

```bash
# Install all packages
ansible-playbook -i inventory/hosts.ini install.yml

# Configure cluster and deploy resources
ansible-playbook -i inventory/hosts.ini configure.yml
```

### 8. Verify the cluster (WSL)

```bash
ansible node1 -i inventory/hosts.ini -m command -a "pcs status" --become
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

### 9. Test the API (WSL)

```bash
curl http://192.168.56.200:8080/status | python3 -m json.tool
```

### 10. Open the live visualiser

Open `ha-demo\ha-failover-demo.html` in your Windows browser. It polls the VIP every second and displays the live counter, active node, and event history.

## Triggering a failover

### Graceful standby (recommended for demo)

```bash
# Put the current primary into standby — resources move to the other node
ansible node1 -i inventory/hosts.ini -m command -a "pcs node standby node1" --become

# Bring it back (resources stay where they are)
ansible node1 -i inventory/hosts.ini -m command -a "pcs node unstandby node1" --become
```

### Hard stop (simulates a crash)

From PowerShell:
```powershell
vagrant halt node1
```

Then from WSL after ~30 seconds:
```bash
ansible node2 -i inventory/hosts.ini -m command -a "drbdadm primary --force r0" --become
ansible node2 -i inventory/hosts.ini -m command -a "pcs resource cleanup" --become
```

Bring node1 back from PowerShell:
```powershell
vagrant up node1
```

Then copy the new SSH key in WSL:
```bash
cp /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo/.vagrant/machines/node1/virtualbox/private_key ~/.ssh/vagrant-keys/node1
chmod 600 ~/.ssh/vagrant-keys/node1
```

### Repeatable demo sequence

```bash
# Failover to node2
ansible node1 -i inventory/hosts.ini -m command -a "pcs node standby node1" --become
ansible node1 -i inventory/hosts.ini -m command -a "pcs node unstandby node1" --become

# Failover back to node1
ansible node2 -i inventory/hosts.ini -m command -a "pcs node standby node2" --become
ansible node2 -i inventory/hosts.ini -m command -a "pcs node unstandby node2" --become
```

## x86_64 specific notes

### DRBD disk device naming
On x86_64, VirtualBox may present the OS disk and DRBD disk in different orders on different VMs (sda/sdb may be swapped). This branch uses a udev rule to create a consistent `/dev/drbd-disk` symlink based on disk size (5GB), ensuring DRBD always uses the correct device regardless of enumeration order.

### SSH key workflow
Unlike macOS where Vagrant manages SSH transparently, on Windows/WSL the SSH keys need to be manually copied to the WSL filesystem and their permissions set. This is a one-time setup per `vagrant destroy`/`vagrant up` cycle.

### Vagrant from PowerShell only
VirtualBox on Windows cannot be controlled from WSL2 directly without version matching and environment variable configuration. Running Vagrant from PowerShell is the most reliable approach.

## STONITH and fencing

### Why STONITH matters

STONITH (Shoot The Other Node In The Head) is a fencing mechanism that forcibly powers off a failed node before promoting the surviving node to Primary. Without it, there is a risk of split-brain — both nodes believing they are Primary and writing to what they think is their own copy of the data, causing permanent data corruption.

### How fencing works in production

| Environment | Fence agent | Mechanism |
|---|---|---|
| Physical servers | `fence_ipmilan` | IPMI/BMC — independent management controller |
| VMware vSphere | `fence_vmware_rest` | vSphere API |
| AWS EC2 | `fence_aws` | AWS API — stop/terminate instance |
| Azure | `fence_azure_arm` | Azure Resource Manager API |
| KVM/libvirt | `fence_virsh` | libvirt API |
| VirtualBox (lab) | Custom script | `VBoxManage controlvm poweroff` |

### Why STONITH is disabled in this lab

VirtualBox does not have a native fence agent in the standard fence-agents package. STONITH is disabled for lab use only. In production, STONITH is non-negotiable for any cluster with shared data.

## Known issues and fixes applied

| Issue | Root cause | Fix |
|---|---|---|
| Module drbd not found | Kernel module package did not match running kernel | Use kernel-uek-modules-{{ ansible_kernel }} |
| Couldn't mount device | Pacemaker resource configured for ext4, disk was XFS | Set drbd_filesystem: xfs in group_vars |
| pip3: command not found | sudo PATH does not include pip3 location | Use executable: /usr/bin/pip3 in pip module |
| disk:Diskless state | DRBD up but no metadata — idempotency check missed this | Detect Diskless in status output and treat as needs create-md |
| meta parameter misconfigured | pcs resource promotable meta params silently ignored | Set meta params separately with pcs resource meta DrbdData-clone |
| ocf:linbit:drbd not installed | drbd-pacemaker package not in install list | Added drbd-pacemaker to 05_corosync_install.yml |
| firewall not running | firewalld not started before firewall tasks | Added systemd: name=firewalld state=started |
| libknet1 not found | Pacemaker deps not in EPEL on OL9 aarch64 | Added enablerepo: ol9_addons to pacemaker install task |
| Hard stop failover fails | No STONITH — Pacemaker will not promote without fencing | Added no-quorum-policy=ignore plus manual drbdadm primary --force |
| Metadata settle timing | drbdadm up fails immediately after create-md | Added 3 second pause after create-md |
| DRBD disk sda/sdb inconsistent | x86_64 VirtualBox presents disks in different order per VM | udev rule creates /dev/drbd-disk symlink based on disk size |
| VBoxManage path error from WSL | WSL paths not understood by Windows VBoxManage | Convert /mnt/c/... paths to C:\... in Vagrantfile |
| SSH key permissions | Windows NTFS permissions too open for SSH | icacls to restrict key + copy to WSL filesystem |
| Vagrant version mismatch | WSL Vagrant version must match Windows Vagrant version | Install matching version in WSL |
| dump-md hangs | drbdadm dump-md hangs when resource is active | Replace with drbdadm show for idempotency check |

## Shutting down

From PowerShell:
```powershell
vagrant halt
```

To destroy and rebuild from scratch (PowerShell then WSL):
```powershell
vagrant destroy -f
vagrant up
```
```bash
# Copy new SSH keys after rebuild
cp /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo/.vagrant/machines/node1/virtualbox/private_key ~/.ssh/vagrant-keys/node1
cp /mnt/c/Users/YourName/Documents/projects/ha-cluster-demo/.vagrant/machines/node2/virtualbox/private_key ~/.ssh/vagrant-keys/node2
chmod 600 ~/.ssh/vagrant-keys/node1
chmod 600 ~/.ssh/vagrant-keys/node2

# Run playbooks
ansible-playbook -i inventory/hosts.ini install.yml
ansible-playbook -i inventory/hosts.ini configure.yml
```
