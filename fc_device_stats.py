#!/usr/local/bin/python3
"""
fc_device_stats.py - Parse a Stealthwatch (SW) Flow Collector (FC) device stats.

Make sure passwordless ssh works on the remote FC.

This has been tested on python3.7.5, highly recomend running from a virtual
environment.
"""

import argparse
import sys
import time
from argparse import RawDescriptionHelpFormatter
from os import path

import pandas as pd
import yaml
from paramiko import SSHClient
from scp import SCPClient
import numpy


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
        self.total_fc_data_1_cycle = ""
        self.total_fc_data_1_cycle_prev = ""
        self.from_fc = "/lancope/var/sw/today/data/exporter_device_stats.txt"
        self.to_user = "/tmp/exporter_device_stats.text"
        self.to_user_nt = "/tmp/exporter_device_stats.txt"
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
                for flow_collector in obj:
                    print(flow_collector)

    def data_runner(self):
        """Runner that repeatedly retrieves FC data and processes it."""
        while True:
            for _, obj in self.config.items():
                for flow_collector in obj:
                    print("Getting data set...")
                    self.get_fc_file(
                        flow_collector["fc_ip"],
                        flow_collector["fc_username"],
                        flow_collector["fc_password"],
                    )
                    self.cln_fc_file()
            self.process_data()
            time.sleep(self.retry)  # Wait ten minutes

    def get_fc_file(self, fc_ip, fc_username, fc_password):
        """
        Connect to the Flow Connector scp the file:
        '/lancope/var/sw/today/data/exporter_device_stats.txt' to /tmp.
        """
        print(f"SSH connect to Flow Collector: {fc_ip}")
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
        print(f"Remote: SCP output {self.from_fc} to {self.to_user}")
        scp = SCPClient(ssh.get_transport(), progress4=progress4)
        scp.get(self.from_fc, self.to_user)
        scp.close()

    def cln_fc_file(self):
        """Clean up the file so its ready to be added to a python pandas.

        Add the data to a working pandas series.
        """
        if not path.exists(self.to_user):
            print(f"Could not find {self.to_user}")
            sys.exit(1)
        else:
            if self.verbose:
                print(f"Successfully found {self.to_user}\n")

        # This text file is nasty
        # It has spaces between header titles and tabs between columns
        print(f"Cleaning: {self.to_user} to {self.to_user_nt}")

        input_file = open(self.to_user, "r")
        export_file = open(self.to_user_nt, "w")
        for line in input_file:
            new_line = line.replace(" ", "_").replace("\t", " ")
            export_file.write(new_line)
        input_file.close()
        export_file.close()

        # Add this FC data to total
        print(f"Adding {self.to_user_nt} to FC data...")
        fc_data = pd.read_csv(self.to_user_nt, sep=" ")

        if not self.first_time:
            # basic merge but not aggregating data
            # pd.merge(self.total_fc_data_1_cycle, fc_data, on="Exporter_Address", how="outer")
            self.total_fc_data_1_cycle.merge(fc_data, on="Exporter_Address", how="outer").groupby(
                ["Exporter_Address"], as_index=False
            ).agg(numpy.sum)
        else:
            self.total_fc_data_1_cycle = fc_data

        if self.verbose:
            print(f"Total data: {self.total_fc_data_1_cycle}")

    def process_data(self):
        """Compare data sets.

        At this point we have all the FC's data and this method should be
        called once per cycle.
        """
        print("Gathered and cleaned all FCs data, lets process it...")

        # Columns we are interested in
        self.total_fc_data_1_cycle = self.total_fc_data_1_cycle[
            ["Exporter_Address", "Current_NetFlow_bps"]
        ]

        # Add new column with a status up or down based on the BPS on the FC
        print("Adding Status based on Current Netflow BPS...")
        self.total_fc_data_1_cycle["Status"] = (
            self.total_fc_data_1_cycle.Current_NetFlow_bps > 0
        ).map({True: "Up", False: "Down"})

        # If no previous data then just return and wait for next loop
        if self.first_time:
            print("First time - nothing to compare")
            self.total_fc_data_1_cycle_prev = self.total_fc_data_1_cycle
            print(f"New previous data saved:\n{self.total_fc_data_1_cycle_prev}")
            self.first_time = False
            return

        # Save latest data to previous
        print(f"Previous data:\n{self.total_fc_data_1_cycle_prev}")
        print(f"Latest data:\n{self.total_fc_data_1_cycle}")
        self.total_fc_data_1_cycle_prev = self.total_fc_data_1_cycle

        # Compare latest and previous data and point out any changes
        comp_fc_data_1_cycle = self.total_fc_data_1_cycle
        comp_fc_data_1_cycle["Status_Prev"] = self.total_fc_data_1_cycle_prev["Status"]
        comp_fc_data_1_cycle["Status_Change"] = (
            comp_fc_data_1_cycle.Status != self.total_fc_data_1_cycle_prev.Status_Prev
        ).map({True: "Changed", False: "No Change"})

        print(f"\nComparison between current and previous data:\n{comp_fc_data_1_cycle}")


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
