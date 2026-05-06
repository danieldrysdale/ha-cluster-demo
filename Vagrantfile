# -*- mode: ruby -*-
# vi: set ft=ruby :

# ============================================================
# Vagrantfile — Two-node Oracle Linux 9 HA Cluster
# ============================================================
# x86_64 (Intel/AMD) with VirtualBox
#
# Usage:
#   vagrant up              — create and provision both nodes
#   vagrant up node1        — create node1 only
#   vagrant ssh node1       — SSH into node1
#   vagrant halt            — shut down both nodes
#   vagrant destroy -f      — delete both VMs completely
#   vagrant provision       — re-run Ansible provisioner
#
# Prerequisites:
#   brew install --cask vagrant
#   vagrant plugin install vagrant-vbguest
#   brew install ansible
# ============================================================

BOX_NAME    = "oraclelinux/9"
BOX_URL     = "https://oracle.github.io/vagrant-projects/boxes/oraclelinux/9.json"

# Second disk for DRBD — one per node
DRBD_DISK_SIZE_GB = 5

# Node definitions
NODES = [
  { name: "node1", ip: "192.168.56.101", memory: 2048, cpus: 2 },
  { name: "node2", ip: "192.168.56.102", memory: 2048, cpus: 2 },
]

Vagrant.configure("2") do |config|

  # ----------------------------------------------------------
  # Base box — Oracle Linux 9 (Intel/AMD)
  # ----------------------------------------------------------
  config.vm.box     = BOX_NAME
  config.vm.box_url = BOX_URL

  # Disable automatic box update checks (speeds up vagrant up)
  config.vm.box_check_update = false

  # Disable vagrant-vbguest auto-update (can cause issues on ARM)
  if Vagrant.has_plugin?("vagrant-vbguest")
    config.vbguest.auto_update = false
  end

  # ----------------------------------------------------------
  # SSH configuration
  # ----------------------------------------------------------
  config.ssh.insert_key = true
  config.ssh.forward_agent = false

  # ----------------------------------------------------------
  # Node loop — define node1 and node2
  # ----------------------------------------------------------
  NODES.each_with_index do |node, index|
    config.vm.define node[:name] do |vm_config|

      vm_config.vm.hostname = node[:name]

      # NAT interface (Vagrant default — for internet access)
      # Host-only interface — cluster heartbeat and replication
      vm_config.vm.network "private_network",
        ip: node[:ip],
        virtualbox__intnet: false,
        nic_type: "virtio"

      # --------------------------------------------------------
      # VirtualBox provider settings
      # --------------------------------------------------------
      vm_config.vm.provider "virtualbox" do |vb|
        vb.name   = "ha-cluster-#{node[:name]}"
        vb.memory = node[:memory]
        vb.cpus   = node[:cpus]

        # Force NIC 2 to virtio for consistent interface naming
        vb.customize ["modifyvm", :id, "--nictype2", "virtio"]
#        vb.customize ["modifyvm", :id, "--uart1", "0x3F8", "4"]
#	if Dir.tmpdir.start_with?('/tmp')
#	  tmpdir = "C:\\Windows\\Temp"
#	else
#	  tmpdir = Dir.tmpdir
#	end
#        vb.customize ["modifyvm", :id, "--uartmode1", "file",
#		      File.join(tmpdir, "#{node[:name]}-console.log")]

        # Disable audio and USB to reduce overhead
        vb.customize ["modifyvm", :id, "--audio", "none"]
        vb.customize ["modifyvm", :id, "--usb", "off"]

        # -------------------------------------------------------
        # Second disk for DRBD (/dev/sdb)
	# Created as a fixed VDI alongside the VM
	# Convert WSL path to Windows path for VBoxManage compatibility
	vagrant_dir = File.dirname(File.expand_path(__FILE__))
	if vagrant_dir.start_with?('/mnt/')
	  # Running from WSL — convert to Windows path
	  parts = vagrant_dir.split('/')
	  drive = parts[2].upcase
	  rest = parts[3..].join('\\')
	  windows_dir = "#{drive}:\\#{rest}"
	else
	  windows_dir = vagrant_dir
	end

	drbd_disk = File.join(
	  windows_dir,
	  ".vagrant",
	  "#{node[:name]}-drbd.vdi"
	)

        unless File.exist?(drbd_disk)
          vb.customize [
            "createhd",
            "--filename", drbd_disk,
            "--size",     DRBD_DISK_SIZE_GB * 1024,
            "--format",   "VDI",
            "--variant",  "Fixed"
          ]
        end

        vb.customize ["storageattach", :id,
          "--storagectl", "SATA Controller",
          "--port",       1,
          "--device",     0,
          "--type",       "hdd",
          "--medium",     drbd_disk
        ]
      end

      # --------------------------------------------------------
      # Shell bootstrap — create vmuser with sudo and SSH key
      # --------------------------------------------------------
      # The Vagrant default user is 'vagrant'. We create 'vmuser'
      # to match the inventory and real-world convention.
      # --------------------------------------------------------
      vm_config.vm.provision "shell", name: "bootstrap", inline: <<~SHELL
        set -e

        # Create vmuser if it doesn't exist
        if ! id vmuser &>/dev/null; then
          useradd -m -s /bin/bash vmuser
          echo "vmuser ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vmuser
          chmod 440 /etc/sudoers.d/vmuser
        fi

        # Copy Vagrant's SSH key to vmuser so Ansible can connect
        mkdir -p /home/vmuser/.ssh
        cp /home/vagrant/.ssh/authorized_keys /home/vmuser/.ssh/
        chown -R vmuser:vmuser /home/vmuser/.ssh
        chmod 700 /home/vmuser/.ssh
        chmod 600 /home/vmuser/.ssh/authorized_keys

        echo "Bootstrap complete — vmuser ready"
      SHELL

      # --------------------------------------------------------
      # Ansible provisioner — runs on the last node only
      # --------------------------------------------------------
      # We wait until both VMs exist before running Ansible
      # so the playbook can target both nodes simultaneously.
      # --------------------------------------------------------
      if node[:name] == NODES.last[:name]
        vm_config.vm.provision "ansible" do |ansible|
          ansible.playbook       = "site.yml"
          ansible.inventory_path = "inventory/hosts.ini"
          ansible.limit          = "all"
          ansible.verbose        = false

          # Pass the Vagrant-managed SSH key to Ansible
          ansible.raw_ssh_args = [
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
          ]

          ansible.extra_vars = {
            ansible_user:                    "vmuser",
            ansible_ssh_private_key_file:    ".vagrant/machines/node1/virtualbox/private_key",
            ansible_become:                  true,
            ansible_become_method:           "sudo",
            ansible_ssh_common_args:         "-o StrictHostKeyChecking=no",
          }
        end
      end

    end
  end

end
