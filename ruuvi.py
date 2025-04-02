import asyncio
from bleak import BleakScanner
import struct
from typing import Tuple
import logging
import queue
import threading

LOG = logging.getLogger("main")


class Ruuvi:
    def __init__(self, config):
        self.sensors = {x[0]: x[1] for x in config["sensors"]}
        self.queue = queue.Queue()
        self.exit_event = asyncio.Event()

    @staticmethod
    def _ruuvi_df5_decode_data(data: str):
        """
        Decode sensor data.
        """

        def _get_temperature(data: bytes) -> float | None:
            """Return temperature in celsius"""
            if data[1] == -32768:
                return None

            return round(data[1] / 200, 2)

        def _get_humidity(data: bytes) -> float | None:
            """Return humidity %"""
            if data[2] == 65535:
                return None

            return round(data[2] / 400, 2)

        def _get_pressure(data: bytes) -> float | None:
            """Return air pressure hPa"""
            if data[3] == 0xFFFF:
                return None

            return round((data[3] + 50000) / 100, 2)

        def _get_acceleration(data: bytes) -> None | Tuple[int, int, int]:
            """Return acceleration mG"""
            if data[4] == -32768 or data[5] == -32768 or data[6] == -32768:
                return None

            return data[4:7]  # type: ignore

        def _get_powerinfo(data: bytes) -> Tuple[int, int]:
            """Return battery voltage and tx power"""
            battery_voltage = data[7] >> 5
            tx_power = data[7] & 0x001F

            return (battery_voltage, tx_power)

        def _get_battery(data: bytes) -> int | None:
            """Return battery mV"""
            battery_voltage = _get_powerinfo(data)[0]
            if battery_voltage == 0b11111111111:
                return None

            return battery_voltage + 1600

        def _get_txpower(data: bytes) -> int | None:
            """Return transmit power"""
            tx_power = _get_powerinfo(data)[1]
            if tx_power == 0b11111:
                return None

            return -40 + (tx_power * 2)

        def _get_movementcounter(data: bytes) -> int:
            return data[8]

        def _get_measurementsequencenumber(data: bytes) -> int:
            return data[9]

        def _get_mac(data: bytes):
            return "".join(f"{x:02x}" for x in data[10:])

        try:
            byte_data: bytes = struct.unpack(">BhHHhhhHBH6B", data)
            acc_x, acc_y, acc_z = _get_acceleration(byte_data)
            return {
                "data_format": 5,
                "humidity": _get_humidity(byte_data),  # type: ignore
                "temperature": _get_temperature(byte_data),  # type: ignore
                "pressure": _get_pressure(byte_data),  # type: ignore
                "acceleration_x": acc_x,  # type: ignore
                "acceleration_y": acc_y,  # type: ignore
                "acceleration_z": acc_z,  # type: ignore
                "tx_power": _get_txpower(byte_data),  # type: ignore
                "battery": _get_battery(byte_data),  # type: ignore
                "movement_counter": _get_movementcounter(byte_data),
                "measurement_sequence_number": _get_measurementsequencenumber(
                    byte_data
                ),
                "mac_pl": _get_mac(byte_data),
            }
        except Exception as err:
            LOG.error(f"Value: {data} not valid: {err}")
            return None

    def _handle_ble_advert(self, device, advertisement_data):
        # The device name seems not working on my board
        # if "ruuvi" not in device.name.lower():

        # On my board, the address has "-" for some reason, other board has ":" ...
        mac = device.address.replace("-", ":")

        if mac not in self.sensors:
            LOG.debug("Ignore as sensor has no name: %s", mac)
            return

        if 1177 not in advertisement_data.manufacturer_data:
            LOG.info("Ignore not 1177: %s", advertisement_data.manufacturer_data.keys())
            return

        ruuvi_pl = advertisement_data.manufacturer_data[1177]

        if ruuvi_pl[0] != 5:
            LOG.info("Ignore as invalid format: ", ruuvi_pl[0])
            return

        data = self._ruuvi_df5_decode_data(ruuvi_pl)
        data["mac"] = device.address
        data["name"] = self.sensors[device.address]
        self.queue.put(data)

    def start(self):
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()

    def _thread_main(self):
        async def capture_ble_advertisements():
            scanner = BleakScanner(self._handle_ble_advert)
            LOG.info("Starting BLE scan...")
            try:
                await scanner.start()
                await self.exit_event.wait()
            except asyncio.CancelledError:
                LOG.error("BLE scanning cancelled.")
            finally:
                await scanner.stop()
                LOG.info("Scanner stopped.")

        async def async_main():
            await capture_ble_advertisements()

        asyncio.run(async_main())
        LOG.info("BLE thread out")
        self.queue.put(None)
