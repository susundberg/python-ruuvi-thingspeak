import argparse
import logging
import sys
import json
import signal

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


def main():
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] > %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    config = {}
    config_get_commandline(config)
    config_get_file(config)
    LOG.info("Using config: %s", config)

    source = Ruuvi(config)
    uploader = ThingSpeak(config)
    source.start()

    while True:
        data = source.queue.get()

        if data is None:
            LOG.info("EOF from source.")
            break
        LOG.info("Got data: %s", data)
        uploader.append(data["name"], data)


if __name__ == "__main__":
    main()
