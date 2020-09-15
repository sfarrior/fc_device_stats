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


class AbortScriptException(Exception):
    """Abort the script and clean up before exiting."""


def parse_args():
    """Parse sys.argv and return args."""
    parser = argparse.ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter,
        description="This tool takes an input file, which is populated with\n"
        "a Vertica FC database query.\n\n"
        "Flow Collector credentials can be added by cli or\n"
        "populated by a ~/parse_biflow.yaml, in the format:\n\n"
        "ip: 10.208.108.101\nusername: root\npassword <mypassword>",
        epilog="E.g.: ./parse_biflow.py 10 -ip 10.90.67.28 -ci 10.90.67.25 -si 216.239.35.12 -st "
        '"2019-11-01 21:41" -lt "2019-11-01 23:41" -fi 68',
    )
    parser.add_argument(
        "-ip",
        "--flow_collector_ip",
        type=str,
        default="None",
        help="IP Address of the Flow Collector to collect Bi-Flow from",
    )
    parser.add_argument(
        "-u",
        "--flow_collector_username",
        type=str,
        default="None",
        help="Username of the Flow Collector to collect Bi-Flow from",
    )
    parser.add_argument(
        "-p",
        "--flow_collector_password",
        type=str,
        default="None",
        help="Password of the Flow Collector to collect Bi-Flow from",
    )
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
        self.from_fc = "/lancope/var/sw/today/data/exporter_device_stats.txt"
        self.to_user = "exporter_device_stats.text"
        self.to_user_nt = "exporter_device_stats.txt"
        self.to_user_csv = "exporter_device_stats.csv"
        self.flow_collector_ip = args.flow_collector_ip
        self.username = args.flow_collector_username
        self.password = args.flow_collector_password
        self.retry = args.retry
        self.first_time = True

        # If neither base config nor CLI has credentials then exit
        if self.flow_collector_ip == "None" or self.username == "None" or self.password == "None":
            print_banner("Error: must supply Flow Collector IP, Username and Password, using CLI")
            sys.exit()

    def data_runner(self):
        """Runner that repeatedly retrieves FC data and processes it."""
        while True:
            self.get_fc_data()
            self.process_file()
            time.sleep(self.retry)  # Wait ten minutes

    def get_fc_data(self):
        """
        Connect to the Flow Connector and query the database.

        Compress the data and SCP the outcome locally to be processed
        """
        print("...Local:  SSH connect to Flow Collector({})".format(self.flow_collector_ip))
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(
            self.flow_collector_ip,
            username=self.username,
            password=self.password,
            look_for_keys=False,
            allow_agent=False,
        )

        # SCP file back home
        print(f"...Remote: SCP output {self.from_fc} to {self.to_user}")
        scp = SCPClient(ssh.get_transport(), progress4=progress4)
        scp.get(self.from_fc, self.to_user)
        scp.close()

    def process_file(self):
        """Use Python Pandas to create a dataset."""

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

        print(self.fc_pandas_data)

        # If no previous data then just return
        if self.first_time:
            print("First time - no previous data")
            self.first_time = False
            self.fc_pandas_data_prev = self.fc_pandas_data
            return

        # Compare with fc_pandas_data_prev
        fc_pandas_data_comp = self.fc_pandas_data
        fc_pandas_data_comp["Status_Prev"] = self.fc_pandas_data_prev["Status"]
        fc_pandas_data_comp["Status_Change"] = (
            self.fc_pandas_data.Status != self.fc_pandas_data.Status_Prev
        ).map({True: "Changed", False: "No Change"})

        # Save latest data to previous
        self.fc_pandas_data_prev = self.fc_pandas_data

        print(fc_pandas_data_comp)


def main():
    """Call everything."""
    args = parse_args()

    try:
        parse = Devicestats(args)

        parse.data_runner()

    except Exception:
        print("Exception caught:")
        print(sys.exc_info())
        raise


if __name__ == "__main__":
    main()
