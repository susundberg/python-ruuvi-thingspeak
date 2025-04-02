#!/usr/bin/env python3

import argparse
import logging
import sys
import json
import signal
import os
import queue
from logging.handlers import RotatingFileHandler


def add_import():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.append(current_dir)


if __name__ == "__main__":
    add_import()

from ruuvi import Ruuvi
from thingspeak import ThingSpeak

LOG = logging.getLogger("main")


def sigint_handler(signal, frame):
    print(f"KeyboardInterrupt at line {frame.f_lineno}")
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


def config_get_commandline(config):
    parser = argparse.ArgumentParser(
        description="RuuviTag listener and upload to thingspeak"
    )
    parser.add_argument("--config-file", default="config.json")
    parser.add_argument("--verbose", action="store_true")
    cmd_args = vars(parser.parse_args())
    config.update(cmd_args)
    config["_cmdline"] = cmd_args


def config_get_file(config: dict):
    with open(config["config_file"], "rb") as fid:
        config_from_file = json.loads(fid.read().decode())
        if "sensors" not in config_from_file:
            raise Exception("Missing 'sensor' definition!")
        config.update(config_from_file)

        # Override again, so that commandline overridesci
        config.update(config["_cmdline"])
        del config["_cmdline"]


def get_config():
    config = {}
    config_get_commandline(config)
    config_get_file(config)
    return config


def main(config):
    LOG.info("Using config: %s", config)

    source = Ruuvi(config)
    uploader = ThingSpeak(config)
    source.start()

    while True:
        try:
            data = source.queue.get(timeout=60.0)
        except queue.Empty:
            uploader.check_upload()
            continue

        if data is None:
            LOG.info("EOF from source.")
            break
        LOG.info("Got data: %s", data)
        uploader.append(data["name"], data)


if __name__ == "__main__":
    config = get_config()

    logging.getLogger().setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    rot_handler = RotatingFileHandler(
        config["logfile"],
        maxBytes=2**18,
        backupCount=1,
    )

    def add_logging_handler(handler):
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    add_logging_handler(rot_handler)

    if config["verbose"]:
        stdout_handler = logging.StreamHandler(sys.stdout)
        add_logging_handler(stdout_handler)
    main(config)
