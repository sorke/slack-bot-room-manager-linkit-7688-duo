import logging
import math
from app import mcu
from config import MOTION_SENSOR
from config import ELECTRICITY_RELAY
from config import ELECTRICITY_SENSOR
from config import TEMP_SENSOR
from config import TEMP_SENSOR_THRESHOLD
from config import LIGHT_SENSOR
from config import LIGHT_SENSOR_THRESHOLD

SENSOR_VCC = 3.3

# sensor v1.0
TEMP_SENSOR_B_VALUE = 3975

class Average_Value:
	def __init__(self, max_values):
		self.max_values = max_values
		self.values = []
		self.avg = 0.0
		
	def add(self, value):
		self.values.append(value)
		
		# remove the oldest entry
		if len(self.values) > self.max_values:
			del self.values[0]
		
		total = 0.0
		for v in self.values:
			total += v
		self.avg = total / len(self.values)
		
	def get_average(self):
		return self.avg
		
	def get_latest_value(self):
		if len(self.values) > 0:
			return self.values[-1]
		return None
		

motion_sensor_active = False

def get_motion_sensor_state():
    global motion_sensor_active
    return motion_sensor_active

def set_motion_sensor_state(state):
    global motion_sensor_active
    motion_sensor_active = state


elect_sensor_avg = Average_Value(10)

elect_relay_active = False

current_temp_value = None

current_light_value = None


def read_mcu():
	# AC current sensor
	elect_sensor = mcu.analog_read(ELECTRICITY_SENSOR)
	ac_current = calc_elect_current(elect_sensor)
	logging.info('ELECTRICITY_SENSOR: %1.1fmA', ac_current)
	elect_sensor_avg.add(ac_current)
	logging.info('Avg AC current: %1.1fmA', elect_sensor_avg.get_average())
	
	# temp sensor
	global current_temp_value
	temp_sensor = mcu.analog_read(TEMP_SENSOR)
	current_temp_value = calc_temp(temp_sensor)
	logging.info('TEMP_SENSOR: %1.0fC', current_temp_value)
	
	# PIR motion sensor
	logging.info('MOTION_SENSOR: %s', get_motion_sensor_state())
	set_motion_sensor_state(False)

	# LDR light sensor
	global current_light_value
	current_light_value = mcu.analog_read(LIGHT_SENSOR)
	logging.info('LIGHT_SENSOR: %d', current_light_value)
	
	# when the 'high' threshold is exceeded, the ELECTRICITY_RELAY is activated (closed)
	# the relay remains active until the sensor value is below the 'low' threshold
	global elect_relay_active
	if current_light_value > LIGHT_SENSOR_THRESHOLD['high']:
		# activate relay to close the blinds
		mcu.digital_write(ELECTRICITY_RELAY, 1)
		elect_relay_active = True
	elif current_light_value < LIGHT_SENSOR_THRESHOLD['low']:
		# remove power, the blinds open automatically
		mcu.digital_write(ELECTRICITY_RELAY, 0)
		elect_relay_active = False
	

def calc_elect_current(value):
	# Based on Grove - Electricity Sensor sample code
	# http://wiki.seeed.cc/Grove-Electricity_Sensor/
	
	# amplitude current (mA)
	amplitude_current = float(value) / 1024 * SENSOR_VCC / 800 * 2000000
	
	# effective value (mA)
	effective_value = amplitude_current / 1.414
	
	logging.debug('value: %d; amplitude_current: %1.1f; effective_value: %1.1f' % \
		(value, amplitude_current, effective_value))
	
	return effective_value


def calc_temp(value):
	# Based on Grove - Temperature Sensor sample code
	# http://wiki.seeed.cc/Grove-Temperature_Sensor/
	resistance = float(1023 - value) * 10000 / value
	
	# temp in celcius - accuracy +/-1.5C
	temp = 1 / (math.log(resistance / 10000) / TEMP_SENSOR_B_VALUE + 1 / 298.15) - 273.15
	
	logging.debug('value: %d; resistance: %1.1f; temp: %1.0f' % (value, resistance, temp))
	
	return temp
	
	
def motion_sensor_callback(data):
	# called by Pymata when the associated latch triggers
	logging.debug('motion_sensor_callback(%s)', data)
	
	set_motion_sensor_state(True)
	
	# re-arm the latch
	mcu.set_digital_latch(MOTION_SENSOR, mcu.DIGITAL_LATCH_LOW, motion_sensor_callback)


def get_status():
	# current status of each of the i/o devices connected to the MCU
	status = {'temp':current_temp_value, 'light':current_light_value,
		'current':elect_sensor_avg, 'relay':elect_relay_active,
		'motion':motion_sensor_active}
	logging.debug('status: %s', status)
	return status