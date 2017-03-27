import logging
import mcu_utils
from app import app, mcu, scheduler, slack_client
from config import MOTION_SENSOR
from config import ELECTRICITY_RELAY
from config import ELECTRICITY_SENSOR
from config import TEMP_SENSOR
from config import LIGHT_SENSOR

# set MCU pin modes
mcu.set_pin_mode(MOTION_SENSOR, mcu.INPUT, mcu.DIGITAL)
mcu.set_digital_latch(MOTION_SENSOR, mcu.DIGITAL_LATCH_LOW,
	mcu_utils.motion_sensor_callback)
mcu.set_pin_mode(ELECTRICITY_RELAY, mcu.OUTPUT, mcu.DIGITAL)
mcu.set_pin_mode(ELECTRICITY_SENSOR, mcu.INPUT, mcu.ANALOG)
mcu.set_pin_mode(TEMP_SENSOR, mcu.INPUT, mcu.ANALOG)
mcu.set_pin_mode(LIGHT_SENSOR, mcu.INPUT, mcu.ANALOG)

if slack_client.rtm_connect():
	scheduler.start()

	app.run(host='192.168.0.17', debug=False)
else:
	logging.critical("Connection failed. Invalid Slack token or bot ID?")