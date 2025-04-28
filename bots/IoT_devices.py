from device import Device


class TermometerAndHumiditySensor1(Device):
    IoT_name = "termometer_and_humidity_sensor"
    uuid_filename = "termometer_and_humidity_sensor1"
    sector = 0
    indicators = ("temperature", "humidity")
    to_change = None


class TermometerAndHumiditySensor2(Device):
    IoT_name = "termometer_and_humidity_sensor"
    uuid_filename = "termometer_and_humidity_sensor2"
    sector = 1
    indicators = ("temperature", "humidity")
    to_change = None


class BrightnessSensor1(Device):
    IoT_name = "brightness_sensor"
    uuid_filename = "brightness_sensor1"
    sector = 0
    indicators = ("brightness",)
    to_change = None


class BrightnessSensor2(Device):
    IoT_name = "brightness_sensor"
    uuid_filename = "brightness_sensor2"
    sector = 1
    indicators = ("brightness",)
    to_change = None


class Heater1(Device):
    IoT_name = "heater"
    uuid_filename = "heater1"
    sector = 0
    indicators = ()
    to_change = "temperature"


class Heater2(Device):
    IoT_name = "heater"
    uuid_filename = "heater2"
    sector = 1
    indicators = ()
    to_change = "temperature"


class Humiditator1(Device):
    IoT_name = "humiditator"
    uuid_filename = "humiditator1"
    sector = 0
    indicators = ()
    to_change = "humidity"


class Humiditator2(Device):
    IoT_name = "humiditator"
    uuid_filename = "humiditator2"
    sector = 1
    indicators = ()
    to_change = "humidity"


class Lamp1(Device):
    IoT_name = "lamp"
    uuid_filename = "lamp1"
    sector = 0
    indicators = ()
    to_change = "brightness"


class Lamp2(Device):
    IoT_name = "lamp"
    uuid_filename = "lamp2"
    sector = 1
    indicators = ()
    to_change = "brightness"