"""
fc_device_stats.py - Parse Stealthwatch (SW) Flow Collector (FC) device stats.

Make sure passwordless ssh works on the remote FC.

This has been tested on python3.8.5, highly recommend running from a virtual
environment.
"""

import argparse
import os
import sys
import time
from argparse import RawDescriptionHelpFormatter

import pandas as pd
import yaml
from paramiko import SSHClient


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
        self.total_fc_data_cycle_current = pd.DataFrame()
        self.total_fc_data_cycle_prev = pd.DataFrame()
        self.fc_datafile_path = "/lancope/var/sw/today/data/exporter_device_stats.txt"
        self.to_user_csv = "persistent_device_stats.csv"

        # Get the config
        with open(args.config, "r") as stream:
            try:
                self.config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        if self.verbose:
            for _, obj in self.config.items():
                for item in obj:
                    print(f"Config Item: {item}")

        # Pull in the retry from config
        self.retry = self.config["Admin"]["retry_interval"]
        print(f"Retry Interval: {self.retry}")

    def data_runner(self):
        """Runner that repeatedly retrieves FC data and processes it."""
        while True:
            for flow_collector in self.config["fcs"]:
                # print("Getting data set...")
                new_fc_data = self.get_fc_file(
                    flow_collector["fc_ip"],
                    flow_collector["fc_username"],
                    flow_collector["fc_password"],
                )
                self.combine_fc_data(new_fc_data)

            # Process all the data collected from FC's
            if self.verbose:
                print(f"Combined Data:\n{self.total_fc_data_cycle_current}")
            self.process_data()

            # Wait retry_interval
            time.sleep(self.retry)

    def get_fc_file(self, fc_ip, fc_username, fc_password):
        """
        Connect to the Flow Connector scp the file:
        '/lancope/var/sw/today/data/exporter_device_stats.txt' to /tmp.
        """

        print(f"\nSSH connect to Flow Collector: {fc_ip}")
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(
            fc_ip,
            username=fc_username,
            password=fc_password,
            look_for_keys=False,
            allow_agent=False,
        )

        sftp = ssh.open_sftp()
        with sftp.open(self.fc_datafile_path) as tsv:
            current_device = pd.read_csv(tsv, sep="\t")

        print("File successfully retrieved and read...")
        # Replace spaces with underscores in column names
        current_device.columns = current_device.columns.str.replace(" ", "_")

        # Add in the FC IP, this is useful for debugging
        current_device["FC_IP"] = fc_ip

        return current_device

    def combine_fc_data(self, new_fc_data):
        """Combine Flow Collector data from one cycle into a pandas Series."""

        print("Adding file to aggregated FC data...")

        # Columns we are interested in
        fc_data = new_fc_data[["Exporter_Address", "Current_NetFlow_bps", "FC_IP"]]

        if self.verbose:
            print(f"New Flow Collector Data:\n{fc_data}")

        self.total_fc_data_cycle_current = (
            pd.concat([self.total_fc_data_cycle_current, fc_data])
            .groupby(["Exporter_Address"], as_index=False)["Current_NetFlow_bps"]
            .sum()
        ).sort_values("Exporter_Address")

    def process_data(self):
        """Compare data sets.

        At this point we have all the FC's data and this method should be
        called once per cycle.
        """
        print("\nGathered and cleaned all FCs data, lets process it...")

        # Add new column with a status up or down based on the BPS on the FC
        print("Adding Status based on Current Netflow BPS...\n")
        self.total_fc_data_cycle_current["Status"] = (
            self.total_fc_data_cycle_current.Current_NetFlow_bps > 0
        ).map({True: "Up", False: "Down"})

        # Display old and current data
        if self.verbose:
            if self.total_fc_data_cycle_prev.empty:
                print("No previous data yet")
            else:
                print(f"Previous data:\n{self.total_fc_data_cycle_prev}")

            print(f"Latest data:\n{self.total_fc_data_cycle_current}")

        if not self.total_fc_data_cycle_prev.empty:
            # Compare latest and previous data and point out any changes
            comp_fc_data_1_cycle = self.total_fc_data_cycle_current
            comp_fc_data_1_cycle["Status_Change"] = (
                comp_fc_data_1_cycle["Status"] != self.total_fc_data_cycle_prev["Status"]
            ).map({True: "Changed", False: "No Change"})

            # Add a datestamp for changed data
            comp_fc_data_1_cycle["Date_Changed"] = (
                comp_fc_data_1_cycle["Status_Change"] == "Changed"
            ).map({True: pd.to_datetime("today"), False: "N/A"})

            print(f"Comparison between current and previous data:\n{comp_fc_data_1_cycle}")

            # Where an interface status has changed, save to persistent file
            comp_fc_data_1_cycle.loc[comp_fc_data_1_cycle["Status_Change"] == "Changed"].set_index(
                "Exporter_Address"
            ).to_csv(self.to_user_csv, mode="a+", header=not os.path.isfile(self.to_user_csv))

        else:
            print("Initial data:")
            print(self.total_fc_data_cycle_current)

        # Save latest data to new previous
        self.total_fc_data_cycle_prev = self.total_fc_data_cycle_current

        # Reset for next loop
        self.total_fc_data_cycle_current = pd.DataFrame()


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
