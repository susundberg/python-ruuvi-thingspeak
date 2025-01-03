import time
import urllib.parse
import urllib.error
import urllib.request

import logging

LOG = logging.getLogger("thing")


class ThingSpeak:
    TO_LOG = "humidity", "temperature", "pressure"

    def __init__(self, config):
        self.url = config["thingspeak_url"]
        self.devices = {
            key: loop for (loop, key) in enumerate(config["sensors"].values())
        }
        self.api_key = config["thingspeak_api_key"]
        self.config_upload_interval = config["thingspeak_interval_s"]
        self.last_update = time.time()

        self.data = {
            x: [
                0.0,
            ]
            * (1 + len(self.TO_LOG))
            for x in config["sensors"].values()
        }
        self.last = {x: 0 for x in config["sensors"].values()}

    def _upload(self, payload):
        encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
        try:
            # Send the request
            with urllib.request.urlopen(self.url, encoded_data) as response:
                result = response.read().decode("utf-8")
                if result == "0":
                    LOG.error("Failed to upload data. Check your API key and fields.")
                else:
                    LOG.info(f"Data uploaded successfully. Entry ID: {result}")
        except urllib.error.URLError as e:
            LOG.error(f"Failed to connect: {e.reason}")
        except Exception as e:
            LOG.error(f"An unexpected error occurred: {e}")

    def _check_upload(self):
        if self.last_update + self.config_upload_interval > time.time():
            return

        payload = {}
        for name in self.devices:
            offset = self.devices[name] * len(self.TO_LOG)

            avg_n = self.data[name][0]
            if avg_n == 0:
                continue
            avgs = [
                self.data[name][x + 1] / self.data[name][0]
                for x in range(len(self.TO_LOG))
            ]
            self.data[name] = [
                0.0,
            ] * (1 + len(self.TO_LOG))

            for loop in range(len(avgs)):
                payload[f"field{offset + loop + 1}"] = avgs[loop]
            LOG.info("Sensor %s avg-n: %d", name, avg_n)
        payload["api_key"] = self.api_key
        LOG.info("Upload payload: %s", payload)
        self._upload(payload)

    def append(self, name, payload):
        if self.last[name] == payload["measurement_sequence_number"]:
            LOG.debug("Ignore payload as same sequence.")
            return
        self.last[name] = payload["measurement_sequence_number"]

        self.data[name][0] += 1
        for loop, key in enumerate(self.TO_LOG):
            self.data[name][1 + loop] += payload[key]
        self._check_upload()



