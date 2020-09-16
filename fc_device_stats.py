#!/usr/local/bin/python3
"""
fc_device_stats.py - Parse a Stealthwatch (SW) Flow Collector (FC) device stats.

Make sure passwordless ssh works on the remote FC.

This has been tested on python3.7.5, highly recomend running from a virtual
environment:
"""

import argparse
import datetime
import os
import re
import socket
import subprocess
import sys
import time
from argparse import RawDescriptionHelpFormatter
from os import path

import pandas as pd
from paramiko import SSHClient
from scp import SCPClient
import yaml


class AbortScriptException(Exception):
    """Abort the script and clean up before exiting."""


def parse_args():
    """Parse sys.argv and return args."""
    parser = argparse.ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter,
        description="Retrieve device statistics from a set of Flow Connectors",
        epilog="E.g.: ./fc_device_stats.py config.yaml",
    )
    parser.add_argument(
        "config",
        help="YAML Config file see config.yaml for example",
    )

    # parser.add_argument(
    #     "-ip",
    #     "--flow_collector_ip",
    #     type=str,
    #     default="None",
    #     help="IP Address of the Flow Collector to collect Bi-Flow from",
    # )
    # parser.add_argument(
    #     "-u",
    #     "--flow_collector_username",
    #     type=str,
    #     default="None",
    #     help="Username of the Flow Collector to collect Bi-Flow from",
    # )
    # parser.add_argument(
    #     "-p",
    #     "--flow_collector_password",
    #     type=str,
    #     default="None",
    #     help="Password of the Flow Collector to collect Bi-Flow from",
    # )
    parser.add_argument(
        "-r",
        "--retry",
        type=int,
        default=600,
        help="Retry - default 10m (600s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="turn on verbose messages, commands and outputs",
    )

    return parser.parse_args()


def run_shell(cli, quiet=False):
    """
    Run a shell command and return the output.

    Print the output and errors if debug is enabled
    Not using logger.debug as a bit noisy for this info
    """
    if not quiet:
        print("...%s" % str(cli))

    process = subprocess.Popen(cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()

    out = out.rstrip()
    err = err.rstrip()

    if str(out) != "0" and str(out) != "1" and out:
        print("  Shell STDOUT output:")
        print()
        print(out)
        print()
    if err:
        print("  Shell STDERR output:")
        print()
        print(err)
        print()

    return out


def print_banner(description):
    """
    Display a bannerized print.

    E.g.     banner("Kubernetes Join")
    """
    banner = len(description)
    if banner > 200:
        banner = 200

    # First banner
    print("\n")
    for _ in range(banner):
        print("*", end="")

    # Add description
    print("\n%s" % description)

    # Final banner
    for _ in range(banner):
        print("*", end="")
    print("\n")


def progress4(filename, size, sent, peername):
    """Define progress callback that prints the current percentage completed for the file."""
    sys.stdout.write(
        "(%s:%s) %s's progress: %.2f%%   \r"
        % (peername[0], peername[1], filename, float(sent) / float(size) * 100)
    )


class Devicestats:
    """
    Common base class for parsing a FCs device stats.

    Create a connection with a remote Flow Connector
    Retrieve /lancope/var/sw/today/data/exporter_device_stats.txt
    SCP output and process data
    """

    pd.options.display.max_rows = None
    pd.options.display.max_columns = None
    pd.options.display.width = None

    num_ran = 0

    def __init__(self, args):
        """Initialize all variables, basic time checking."""
        self.verbose = args.verbose
        self.flow_collector_ip = "None"
        self.username = "None"
        self.password = "None"
        self.fc_pandas_data = ""
        self.fc_pandas_data_prev = ""
        self.global_data = ""
        self.from_fc = "/lancope/var/sw/today/data/exporter_device_stats.txt"
        self.to_user = "exporter_device_stats.text"
        self.to_user_nt = "exporter_device_stats.txt"
        self.to_user_csv = "exporter_device_stats.csv"
        self.retry = args.retry
        self.first_time = True
        self.config = args.config

        # Get the config
        with open(self.config, "r") as stream:
            try:
                self.config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        if self.verbose:
            for _, obj in self.config.items():
                for fc_data in obj:
                    print(fc_data)

    def data_runner(self):
        """Runner that repeatedly retrieves FC data and processes it."""
        while True:
            for _, obj in self.config.items():
                for fc_data in obj:
                    print("Getting data set...")
                    self.get_fc_data(fc_data["fc_ip"], fc_data["fc_username"], fc_data["fc_password"])
                    self.process_file()
            self.process_data()
            del self.global_data
            time.sleep(self.retry)  # Wait ten minutes

    def get_fc_data(self, fc_ip, fc_username, fc_password):
        """
        Connect to the Flow Connector and query the database.

        Compress the data and SCP the outcome locally to be processed
        """
        print(f"...Local:  SSH connect to Flow Collector({fc_ip}, {fc_username}, {fc_password})")
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(
            fc_ip,
            username=fc_username,
            password=fc_password,
            look_for_keys=False,
            allow_agent=False,
        )

        # SCP file back home
        print(f"...Remote: SCP output {self.from_fc} to {self.to_user}")
        scp = SCPClient(ssh.get_transport(), progress4=progress4)
        scp.get(self.from_fc, self.to_user)
        scp.close()

    def process_file(self):
        """Use Python Pandas to create a dataset.

        Grab data and add to a global series.
        """

        if not path.exists(self.to_user):
            print(f"Could not find {self.to_user}")
            sys.exit(1)
        else:
            print(f"Successfully found {self.to_user}\n")

        # This text file is nasty
        # It has spaces between header titles and tabs between columns
        input_file = open(self.to_user, "r")
        export_file = open(self.to_user_nt, "w")
        for line in input_file:
            new_line = line.replace(" ", "_").replace("\t", " ")
            export_file.write(new_line)
        input_file.close()
        export_file.close()

        # At this point it's just processing data
        self.fc_pandas_data = pd.read_csv(self.to_user_nt, sep=" ")

        # Columns we are interested in
        self.fc_pandas_data = self.fc_pandas_data[["Exporter_Address", "Current_NetFlow_bps"]]

        # Add new column with a status up or down based on the BPS on the FC
        self.fc_pandas_data["Status"] = (self.fc_pandas_data.Current_NetFlow_bps > 0).map(
            {True: "Up", False: "Down"}
        )

        # Add to global (per cycle database)
        if self.first_time:
            self.global_data = self.fc_pandas_data
            self.first_time = False
        else:
            self.global_data = self.global_data.append(self.fc_pandas_data, ignore_index=True)

        print(self.global_data)

    def process_data(self):
        """Compare data sets."""
        # If no previous data then just return
        if self.first_time:
            print("First time - no previous data")
            self.fc_pandas_data_prev = self.fc_pandas_data
            return

        # Compare with fc_pandas_data_prev
        # fc_pandas_data_comp = self.global_data
        self.global_data["Status_Prev"] = self.fc_pandas_data_prev["Status"]
        self.global_data["Status_Change"] = (
            self.fc_pandas_data.Status != self.fc_pandas_data.Status_Prev
        ).map({True: "Changed", False: "No Change"})

        # Save latest data to previous
        self.fc_pandas_data_prev = self.global_data

        print(self.global_data)


def main():
    """Call everything."""
    args = parse_args()
    print(args)

    try:
        parse = Devicestats(args)

        parse.data_runner()

    except Exception:
        print("Exception caught:")
        print(sys.exc_info())
        raise


if __name__ == "__main__":
    main()
