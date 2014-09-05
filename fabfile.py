from functools import (partial)
import os
import time

import boto.ec2
from fabric.api import (
    abort,
    env,
    hide,
    run,
    sudo
)
from fabric.context_managers import (
    quiet,
    settings
)

CLOUD_INIT_TMPL = """#cloud-config

ssh_authorized_keys:
  - {0}

packages:
  - git

runcmd:
  - apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 36A1D7869245C8950F966E92D8576A8BA88D21E9
  - sh -c "echo deb https://get.docker.io/ubuntu docker main > /etc/apt/sources.list.d/docker.list"
  - apt-get update
  - apt-get install -y lxc-docker

"""

# This is the official Ubuntu 14.04 LTS AMI, PV edition for us-west-2
# TODO: Make a map here of the appropriate AMI's for all regions
AMI = "ami-5b58266b"


remote_settings = partial(settings, user="ubuntu", warn_only=True)


"""Determine if an instance is a running tc-builder"""
def _running_tc_builder(instance):
    tc_inst = instance.tags.get("Name") == "tc-builder"
    tc_running = instance.state == "running"
    return tc_inst and tc_running


def _make_cloud_init():
    ssh_dir = os.path.expanduser("~/.ssh/")
    pub_file = filter(lambda x: x in ["id_dsa.pub", "id_rsa.pub"],
                      os.listdir(ssh_dir))
    if not pub_file:
        abort("No public ssh identity to use on the provisioned host.")
    with open(os.path.join(ssh_dir, pub_file[0])) as f:
        ssh_key = f.readline().strip()
    return CLOUD_INIT_TMPL.format(ssh_key)


"""Locates a running tc builder instance"""
def _locate_running_tc_builder(conn):
    instances = conn.get_only_instances()
    return filter(_running_tc_builder, instances)


"""Verify a running instance"""
def _verify_running_tc_builder(conn):
    instances = conn.get_only_instances()
    inst = filter(_running_tc_builder, instances)
    if not inst:
        abort("Failure to find a tc-builder instance running.")

    return inst[0]


"""Provisions a Ubuntu 14.04 AWS instance for container building."""
def provision(region="us-west-2"):
    conn = boto.ec2.connect_to_region(region)

    # Verify whether a tc-builder is running yet, if it is, abort
    if _locate_running_tc_builder(conn):
        abort("Found tc-builder instance running.")

    # Verify the security group exists, make it if it doesn't
    if not filter(lambda x: x.name == "tc-builder",
                  conn.get_all_security_groups()):
        tc_sec = conn.create_security_group(
            "tc-builder",
            "Travis Container Builder Policy",
        )
        # Add ssh
        tc_sec.authorize("tcp", "22", "22", "0.0.0.0/0")

    user_data = _make_cloud_init()

    print "Provisioning..."
    # Create our instance, and save the instance id
    res = conn.run_instances(
        AMI,
        user_data = user_data,
        instance_type = "t1.micro",
        security_groups = ["tc-builder"]
    )
    inst = res.instances[0]

    print "Allocated, waiting for running state..."
    while inst.update() != 'running':
        time.sleep(5)
    inst.add_tag("Name", "tc-builder")
    print "Running. Checking for SSH availability..."

    retry = True
    count = 0
    while retry and count < 500:
        try:
            with settings(hide('everything'),
                          host_string=inst.ip_address,
                          warn_only=True):
                result = run("which -a docker")
                if result == "/usr/bin/docker":
                    retry = False
        except:
            pass
        finally:
            count += 1
            time.sleep(5)
    if count >= 500:
        abort("Unable to ssh in.")
    print "Fully available."


"""Removes a running tc-builder if one is found."""
def unprovision(region="us-west-2"):
    conn = boto.ec2.connect_to_region(region)

    # Locate the tc-builder instance
    tc_instances = _locate_running_tc_builder(conn)
    if not tc_instances:
        abort("No tc-builder instance running.")

    tc_instances[0].terminate()


"""Checks out a repo on a remote host and updates it to a specific
   commit

   This runs on a remote host that is assumed to have been configured
   and running by ``provision``.

"""
def checkout(repo, commit, region="us-west-2"):
    conn = boto.ec2.connect_to_region(region)

    # Ensure we have pulled the latest travis-run on the remote host
    inst = _verify_running_tc_builder(conn)

    with remote_settings(host_string=inst.ip_address):
        
