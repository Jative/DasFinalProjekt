from device import Device


class TermometerAndHumiditySensor1(Device):
    IoT_name = "termometer_and_humidity_sensor"
    uuid_filename = "termometer_and_humidity_sensor1"
    sector = 0
    indicators = ("temperature", "humidity")


class TermometerAndHumiditySensor2(Device):
    IoT_name = "termometer_and_humidity_sensor"
    uuid_filename = "termometer_and_humidity_sensor2"
    sector = 1
    indicators = ("temperature", "humidity")


class BrightnessSensor1(Device):
    IoT_name = "brightness_sensor"
    uuid_filename = "brightness_sensor1"
    sector = 0
    indicators = ("brightness",)


class BrightnessSensor2(Device):
    IoT_name = "brightness_sensor"
    uuid_filename = "brightness_sensor2"
    sector = 1
    indicators = ("brightness",)

class Heater1(Device):
    IoT_name = "heater"
    uuid_filename = "heater1"
    sector = 0
    indicators = None