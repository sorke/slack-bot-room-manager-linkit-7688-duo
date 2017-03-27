import logging
from datetime import datetime
from pytz import timezone
import pytz

MINS_IN_HOUR = 60
SECONDS_IN_MIN = 60
DAY_IN_MINS = 24 * MINS_IN_HOUR

TZ = timezone('Europe/Amsterdam')
UTC = pytz.utc

EPOCHE = datetime(1970, 1, 1, tzinfo=None)

def utc_datetime_now():
	dt = local_datetime_now().astimezone(UTC)
	logging.debug('utc_datetime_now(): %s', dt)
	return dt


def utc_date_now():
	return utc_datetime_now().date()


def utc_time_now():
	return utc_datetime_now().time()


def utc_timestamp_now():
	return to_timestamp(utc_datetime_now())


def local_datetime_now():
	dt = TZ.localize(datetime.now())
	logging.debug('local_datetime_now(): %s', dt)
	return dt

def local_date_now():
	return local_datetime_now().date()


def local_time_now():
	return local_datetime_now().time()


def to_timestamp(dt):
	logging.debug('to_timestamp(%s)', dt)
	utc_dt = dt
	if utc_dt.tzinfo:
		utc_dt = utc_dt.replace(tzinfo=None) - utc_dt.utcoffset()
	logging.debug('utc_dt: %s', utc_dt)
	ts = (utc_dt - EPOCHE).total_seconds()
	logging.debug('ts: %d', ts)
	return ts

def to_day_timestamp(dt):
	logging.debug('to_day_timestamp(%s)', dt)
	ts = (datetime(dt.year, dt.month, dt.day, tzinfo=None)- EPOCHE).total_seconds()
	logging.debug('ts: %d', ts)
	utc_offset = dt.utcoffset()
	if utc_offset:
		logging.debug('dt.utcoffset(): %s', utc_offset)
		ts -= utc_offset.total_seconds()
		logging.debug('ts: %d', ts)
	return ts


def is_today(dt):
	return dt.date() == utc_date_now()


def adjust_time(dt, tod_in_mins, force=True):
	d = dt
	t = tod_in_mins
	if force:
		d = dt.replace(hour=t // MINS_IN_HOUR, minute=t % MINS_IN_HOUR, second=0)
	else:
		# assume day is 'now'
		t = d.hour * MINS_IN_HOUR + d.minute
	
		# don't allow tod to be set in the past
		if tod_in_mins > t:
			t = tod_in_mins
			d = dt.replace(hour=t // MINS_IN_HOUR, minute=t % MINS_IN_HOUR, second=0)
	
	return d, t


def convert_date_to_datetime(date, time=None):
	if time == None:
		return TZ.localize(datetime.combine(date, datetime.min.time()))
	 
	return TZ.localize(datetime.combine(date, time))


