# fc_device_stats

This is a tool to pull device stats from a FC. And do something with that data.

User is expected to have root access to the Flow Collectors and root SSH
access.

Basic operations::

    1. Connect to the Flow Collector
    2. Submit a VSQL query in CSV format
    3. Close the connection and create a Pandas dataframe from the CVS file
    4. Parse the data and present to the user.

See ./parse_biflow.py -h for full argument list

## Requirements

Every 10 minutes, 7x24, my four FCs send data from /lancope/var/sw/today/data/exporter_device_stats.txt  to pandas running on a separate redhat unix server.
If just one field must be chosen as the most important one, it’s the 44th field “Current NetFlow bps”
I don’t know what pandas ingestion will look like
From pandas, there is automation that asks questions via a script that runs on a regular interval and does stuff (like send syslog, send email, populates a web page) according to the result.
Define “down” as : =0 in the Current NetFlow bps field
Define “up” as: >0 in the Current NetFlow bps field
What exporter+interface has gone down in the last 10 minutes?
When netflow moves from one FC to another, it’ll start reporting as zero on the old one and >0 on the new one. Ignore the zero bps reported from the old FC.
What exporter+interface has come back up in the last 10 minutes?
What is the cumulative down time for any given exporter+interface in the last month?
What is the cumulative down time for all our exporter+interfaces in the last month?

## Install environment

### Upgrade pip3

```bash
python3 -m pip install --upgrade pip
```

### Install Virtual Env

```bash
pip3 install virtualenv
```

### Create a python3 virtual environment

```bash
virtualenv -p python3 fc_device_stats
```

### Activate virtual env

```bash
source fc_device_stats/bin/activate
```

### Install requirements

```bash
cd ~/fc_device_stats
pip3 install -r requirements.txt
```
