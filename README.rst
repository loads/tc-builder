==============================
Travis-based Container Builder
==============================

This set of fabric tasks automate the task of building of a Docker container
provided a DVCS repository that contains a ``.travis.yml`` file. The resulting
container will be configured to run the main script as the Docker entrypoint.
It can then save the resulting container as a tarball, upload it to S3, etc.

Installing
==========

This script can run locally and use a local docker to build the container, or
provision a remote AWS instance and build the container there. It can also use
an existing remote instance that already has the necessary commands in place.

Requirements on the host running the fabric commands:

1. scp
2. sshd
3. docker
4. git

Requirements to run fabric:

1. Python
2. fabric

Usage
=====

To provision a remote machine to build the container on (You must have AWS
config where boto expects it):

.. code-block:: bash

    > fab provision

Create a container based on a repository and commit:

.. code-block:: bash

    > fab REPO_URL REPO_COMMIT
