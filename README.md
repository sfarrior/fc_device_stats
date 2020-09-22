# fc_device_stats

This is a tool to pull device stats from a Flow Collector (FC). And do
something with that data in order to get early alerting on any interface status
changes.

Basic operations::

    1. Connect to the Flow Collector
    2. Pull down device stats file
    3. Close the connection and create a Pandas dataframe from the CVS file
    4. Parse the data and present to the user.

User is expected to have root access to the Flow Collectors and root SSH
access.

## Requirements

The ability to poll multiple Flow Collectors to determine if particular
interfaces have a change in status, that might indicate something has gone
wrong either hardware or software.

Each FC updates: ```/lancope/var/sw/today/data/exporter_device_stats.txt```
every 1 to 5 minutes, therefore on a retry interval that should be
configurable, poll these files to see what the NetFlow BPS per interface is. As
flows can move from one FC to another, aggregate the data and see if a
particular interface is reporting zero bytes.

Define “down” as: == 0 in the Current NetFlow bps field
Define “up” as: > 0 in the Current NetFlow bps field

Information to provide:

- What exporter+interface has gone down in the last 10 minutes?
- When netflow moves from one FC to another, it’ll start reporting as zero on
  the old one and >0 on the new one. Ignore the zero bps reported from the old
  FC.
- What exporter+interface has come back up in the last 10 minutes?
- What is the cumulative down time for any given exporter+interface in the last month?
- What is the cumulative down time for all our exporter+interfaces in the last month?

In addition:

- Write the code in a way that is easily expandable for future requirements.
- Provide the configuration in a human readible manner (like YAML for example).
- Dockerize the application for installation ease.
- Provide persistent logging.
- Provide the ability to send logs to a log server.

## Install environment

### PIP

#### Upgrade pip3

    python3 -m pip install --upgrade pip

#### Install Virtual Env

    pip3 install virtualenv

#### Create a python3 virtual environment

    virtualenv -p python3 fc_device_stats

#### Activate virtual env

    source fc_device_stats/bin/activate

#### Install requirements

    cd ~/fc_device_stats
    pip3 install -r requirements.txt

### Docker

#### Build the docker image

Install docker in your environment

    docker build -t rwellum/fc_device_stats .

**Note this step is for the tool creator.**

#### Push to dockerhub

Note this will change to the permenant home in the future.

    docker push rwellum/fc_device_stats

**Note this step is for the tool creator.**

#### Run the docker image

Working assumption is that user has docker installed and can run a simple
container like:

    docker run hello-world

**If this fails, stop and fix your docker installation.**

**Note: edit config_working.yaml to add your retry interval and FC's information.**

    docker run \
    -it --rm \
    --volume ${SSH_AUTH_SOCK}:/ssh-agent --env SSH_AUTH_SOCK=/ssh-agent \
    --volume ${HOME}/.ssh/:/root/.ssh \
    --volume `pwd`/config_working.yaml:/app/config.yaml \
    rwellum/fc_device_stats

## Todo's

Todo's from first customer demo:

### Done

- requirements.txt - done
- Persistent reporting on down time - done
- dockerize - done (pushed to dockerhub, tested)
- Debug and check data - done

### Not Done

- Send syslog - create alert method (log/email etc)
- Add yaml syslog target receiver
