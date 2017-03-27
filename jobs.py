import bookings
from datetime import datetime, timedelta
import dtutils
import logging
import mcu_utils
import slackutils
import string
import sys
import time
import unicodedata
from app import db, models, slack_client
from bookings import MIN_SLOT_DURATION
from bookings import SECONDS_IN_MIN
from config import BOT_ID
from config import TEMP_SENSOR_THRESHOLD
from config import LOW_TEMP_MESSAGE
from config import HIGH_TEMP_MESSAGE

from dtutils import MINS_IN_HOUR
from sqlalchemy import text

AT_BOT = "<@" + BOT_ID + ">"

# commands
FREE_COMMAND = 'free'
BOOK_COMMAND = 'book'
SHOW_COMMAND = 'show'
NAME_COMMAND = 'name'
STATUS_COMMAND = 'status'

# command options
NOW = 'now'
TODAY = 'today'
THIS = 'this'
TOMORROW = 'tomorrow'
WEEKDAYS = {'monday':0, 'tuesday':1, 'wednesday':2, 'thursday':3, 'friday':4, 
	'saturday':5, 'sunday':6, 'mon':0, 'tue':1, 'wed':2, 'thu':3, 'fri':4, 'sat':5,
	'sun':6, 'tues':1, 'thur':3, 'thurs':3}
TOD_MODS = {'morning':bookings.MORNING['start'],
	'lunchtime':bookings.LUNCHTIME['start'],'afternoon':bookings.AFTERNOON['start']}
ALL = 'all'


def format_slack_slot(slack_date, date_ts, slot):
	# formats a single booking suggestions ready for sending to slack
	t = slackutils.format_slack_time(date_ts, slot.start)
	if slot.booking and slot.booking.name:
		return '%s at %s for %d mins - %s' % (slack_date, t, slot.duration, slot.booking.name)
	else:
		return '%s at %s for %d mins' % (slack_date, t, slot.duration)
	

def format_slack_booking(slack_date, date_ts, start_time, duration=0, full=False):
	# formats a single booking ready for sending to slack
	t = slackutils.format_slack_time(date_ts, start_time)
	if full:
		return ('%s at %s for %d mins' % (slack_date, t, duration))

	return ('%s at %s' % (slack_date, t))


def format_free_response(suggested_slots, no_bookings, day, tod_in_mins):
	# formats the response to a FREE_COMMAND ready for sending to slack
	if no_bookings:
		msg = "I'm free "
		if dtutils.is_today(day):
			if len(suggested_slots) == 0 and tod_in_mins > bookings.LAST_SLOT_START:
				msg += "but I'm not allowed to make bookings after %02d:%02d" % \
					(bookings.LAST_SLOT_START / MINS_IN_HOUR, \
					 bookings.LAST_SLOT_START % MINS_IN_HOUR)
				return msg
				
			msg += "for the rest of the day"
			
		else:
			msg += "all day"
			
		if len(suggested_slots) == 1:
			msg += '\n\nThis is the best option:'
		elif len(suggested_slots) > 1:
			msg += '\n\nThese are the best options:'

		day_ts = dtutils.to_day_timestamp(day)
		d = slackutils.format_slack_date(day)
		count = 1
		for slot in suggested_slots:
			msg += ('\n`%d` %s' % (count, format_slack_slot(d, day_ts, slot)))
			count += 1
	else:
		msg = ''
		earliest_start = bookings.DAY_IN_MINS
		day_ts = dtutils.to_day_timestamp(day)
		d = slackutils.format_slack_date(day)
		count = 1
		for slot in suggested_slots:
			if slot.start < earliest_start:
				earliest_start = slot.start
			msg += ('\n`%d` %s' % (count, format_slack_slot(d, day_ts, slot)))
			count += 1

		t = slackutils.format_slack_time(day_ts, earliest_start)
		if len(suggested_slots) == 1:
			msg = "I'm booked until " + t + ", then I have this option available:" + msg
		elif len(suggested_slots) > 1:
			msg = "I'm booked until " + t + ", then I have these options available:" + msg

	return msg


def format_slack_status(status):
	# formats a status msg ready for sending to slack
	msg = "Sorry but I'm not able to share my status at this time"
	if status:
		msg = 'Current status:\n'
		if status['motion']:
			msg += 'Occupied\n'
		else:
			msg += 'Unoccupied\n'
			
		if status['relay']:
			msg += 'The blinds are closed\n'
		else:
			msg += 'The blinds are open\n'
		
		if status['temp']:
			msg += 'Temperature: %1.0fC\n' % (status['temp'])
		
		if status['current'] and status['current'].get_latest_value() > 0:
			msg += 'The wall socket is in use: %1.1fmA (5 min average: %1.1fmA)' % \
				(status['current'].get_latest_value(), status['current'].get_average())
		else:
			msg += 'The wall sock is not in use'
			
	return msg


def update_slack_user(sid):
	# fetches the current user.info from slack and stores it in the db
	slack_user = slackutils.get_slack_user(sid)
	if slack_user:
		user = models.SlackUser.query.filter(models.SlackUser.sid == sid).first()
		if user:
			user.name = slack_user['name']
			user.real_name = slack_user['real_name']
			user.image_48 = slack_user['image_48']
		else:
			user = models.SlackUser(sid=slack_user['id'], name=slack_user['name'],
				real_name=slack_user['real_name'], image_48=slack_user['image_48'])
		db.session.add(user)
		db.session.commit()	


# used to remove punctuation - py2
NO_PUNCT_TRANS = dict.fromkeys(x for x in xrange(sys.maxunicode) 
					if unicodedata.category(unichr(x)).startswith('P'))

def tokenise(s):
	# convert to lowercase and remove punctuation before splitting
	return s.translate(NO_PUNCT_TRANS).lower().split()
	

def strip_whitespace(s):
	return s.strip(string.whitespace)
	

def handle_command(command, channel, user):
	# processes messages directed at the bot and determines if they
	# are valid commands.
	# if they are, then the command is acted on, otherwise, the reply is a help message
	logging.debug('command: %s', command)

	tokens = tokenise(command)
	logging.debug('tokens: %s', tokens)
	
	response = "Not sure what you mean.\nUse the *" + FREE_COMMAND + \
			   "* command followed by *now*, *tomorrow* or the name of a day to book me"
	
	# all dates and times are local
	if tokens[0] == FREE_COMMAND:
		# get a list of suggested booking options for the specified day and time
		# free <now|today|tomorrow|(day of week)|(this morning|lunchtime|afternoon|evening)>
		response = 'Use *' + FREE_COMMAND + '* and specify a day, for example *now* or \
			*this afternoon* or *tomorrow* or *Mon* or *friday morning'
		if len(tokens) >= 2:
			day = dtutils.local_datetime_now()
			tod_in_mins = day.hour * MINS_IN_HOUR + day.minute
			logging.debug('now day: %s; tod_in_mins: %d' % (day, tod_in_mins))
			if tokens[1] == NOW or tokens[1] == TODAY \
				or (tokens[1] == THIS and len(tokens) >= 3 and tokens[2] in TOD_MODS):
				if tokens[1] == THIS:
					day, tod_in_mins = dtutils.adjust_time(day, TOD_MODS[tokens[2]],
						force=False)			
			elif tokens[1] == TOMORROW:
				day = day + timedelta(days=1)
				if len(tokens) >= 3 and tokens[2] in TOD_MODS:
					day, tod_in_mins = dtutils.adjust_time(day, TOD_MODS[tokens[2]])			
				else:
					day, tod_in_mins = dtutils.adjust_time(day, bookings.MORNING['start'])
			elif tokens[1] in WEEKDAYS:
				weekday = WEEKDAYS[tokens[1]]
				today = day.weekday()
				offset = weekday - today
				if weekday <= today:
					offset += 7
				day = day + timedelta(days=offset)
				if len(tokens) >= 3 and tokens[2] in TOD_MODS:
					day, tod_in_mins = dtutils.adjust_time(day, TOD_MODS[tokens[2]])			
				else:
					day, tod_in_mins = dtutils.adjust_time(day, bookings.MORNING['start'])

			logging.debug('adjusted day: %s; tod_in_mins: %d' % (day, tod_in_mins))
			if tod_in_mins != None:
				# check when the room is free
				available_slots, no_bookings = bookings.available_slots(day, tod_in_mins,
					bookings.MIN_SLOT_DURATION, user)
		
				# create a list of suggested bookings
				suggested_slots = bookings.suggest_slots(available_slots,
					MIN_SLOT_DURATION * 2)
		
				# store them, awaiting confirmation
				count = 1
				for slot in suggested_slots:
					slot.ref = count
					bookings.create_unconfirmed_booking(day, slot, user)
					count += 1
		
				# prepare the slack response
				response = format_free_response(suggested_slots, no_bookings, day,
					tod_in_mins)
	elif tokens[0] == BOOK_COMMAND:
		# confirm one of the previously suggested booking options
		# optionally, give the booking a name
		# book <option>
		response = 'Use *' + BOOK_COMMAND + '* and a valid option number.'
		if len(tokens) >= 2:
			response = "Sorry, I couldn't find option `%s`\n" % (tokens[1],) + response
			try:
				ref = int(tokens[1])
				if ref >= 1 and ref <= 4:
					name = None
					if len(tokens) >= 4 and tokens[2] == NAME_COMMAND:
						name = strip_whitespace(command.split(NAME_COMMAND, 1)[1])
						logging.debug('new booking name is: %s', name)
							
					booking = bookings.confirm_booking(user, ref, 1, name=name,
						set_reminder=True, slack_channel=channel)
					if booking:
						# so we have the latest details for the room display
						update_slack_user(user)
						
						day = dtutils.convert_date_to_datetime(booking.start_date)
						day_ts = dtutils.to_day_timestamp(day)
						d = slackutils.format_slack_date(day)
						response = 'Great!'
						if name:
							response += " '%s' is booked" % (booking.name)
						response = response + ' for %s' % \
							(format_slack_booking(d, day_ts, booking.start_time))			
			except ValueError:
				# the specified option wasn't an integer
				pass
	elif tokens[0] == SHOW_COMMAND:
		# get a list of all the specified user's current and future booking
		# or optionally, a list of future and future bookings for all users 
		# show <all>
		booked_slots = []
		if len(tokens) >= 2 and tokens[1] == ALL:
			booked_slots = bookings.get_bookings(None)
		else:
			booked_slots = bookings.get_bookings(user)

		count = 0
		booking_refs = []
		response = ''
		for slot in booked_slots:
			date = dtutils.convert_date_to_datetime(slot.date)
			d = slackutils.format_slack_date(date)
			date_ts = dtutils.to_day_timestamp(date)
			if slot.booking.booker_sid == user:
				count += 1
				slot.ref = count
				booking_refs.append(slot)
				response += ('\n`%d` %s' % (count, format_slack_slot(d, date_ts, slot)))
			else:
				response += ('\n%s' % (format_slack_slot(d, date_ts, slot)))
		
		# store the refs we show the user, so they can use them with later commands
		if len(booking_refs) > 0:
			bookings.set_booking_refs(user, booking_refs)
			
		if count == 0:
			response = "You don't have any bookings" + response
		else:
			response = 'You have %d bookings' % (count) + response
	elif tokens[0] == NAME_COMMAND:
		# change the name of the specified booking
		# name <option> <booking name>
		response = 'Use *' + NAME_COMMAND + '* and a valid option number.'
		if len(tokens) >= 3:
			response = "Sorry, I couldn't find option `%s`\n" % (tokens[1]) + response
			try:
				ref = int(tokens[1])
				if ref >= 1:
						name = strip_whitespace(command.split(tokens[1], 1)[1])
						logging.debug('new booking name is: %s', name)
						bookings.update_booking_by_ref(user, ref, name=name)
						response = "Done!\nChanged the name to '%s'" % (name)			
			except ValueError:
				# the specified option wasn't an integer
				pass			
	elif tokens[0] == STATUS_COMMAND:
		# get the status of room, including sensor info
		# status
		status = mcu_utils.get_status()
		response = format_slack_status(status)

	logging.debug('response: %s', response)

	slack_client.api_call("chat.postMessage", channel=channel, text=response, as_user=True)


def	read_slack_rtm():
	# scheduled job
	# processes the latest messages from slack
	with db.app.app_context():
		event = slackutils.filter_slack_events(slack_client.rtm_read())
		if event:
			if event['type'] == slackutils.MESSAGE_EVENT_TYPE:
				command = event['message'].split(AT_BOT)[1]
				handle_command(command, event['channel'], event['user'])


REMINDER_FILTER_STMT = text('send_at >= :earlier and send_at < :later')

def send_reminders():
	# scheduled job
	# checks for any booking reminders that need to be sent
	with db.app.app_context():
		now_ts = dtutils.utc_timestamp_now()
		reminders = models.Reminder.query.filter(REMINDER_FILTER_STMT). \
			params(earlier=now_ts - SECONDS_IN_MIN / 2, \
				later=now_ts + SECONDS_IN_MIN / 2).all()
	
		if reminders:
			# get the status of room, including sensor info
			status = mcu_utils.get_status()
			
			count = 0
			for reminder in reminders:
				msg = reminder.text
				if status['temp']:
					if status['temp'] <= TEMP_SENSOR_THRESHOLD['low']:
						msg += '\n' + LOW_TEMP_MESSAGE
					elif status['temp'] >= TEMP_SENSOR_THRESHOLD['high']:
						msg += '\n' + HIGH_TEMP_MESSAGE
				slack_client.api_call("chat.postMessage", channel=reminder.slack_channel,
					text=msg, as_user=True)
				count += 1
		logging.info('Reminders sent: %s', count)		


def cleanup_bookings():
	# scheduled job
	# removes any old booking, booking suggestions and reminders
	with db.app.app_context():
		now = dtutils.utc_datetime_now()
		now_date = now.date()
		now_ts = now.timestamp()

		# remove old reminders
		models.Reminder.query.filter(models.Reminder.send_at < now_ts). \
			delete(synchronize_session=False)
		
		# remove old bookings
		models.ConfirmedBooking.query.filter(models.ConfirmedBooking.start_date < now_date). \
			delete(synchronize_session=False)
		
		# remove old unconfirmed bookings
		models.UnconfirmedBooking.query.filter(models.UnconfirmedBooking.start_date < now_date). \
			delete(synchronize_session=False)
		
		db.session.commit()

def mcu_handler():
	# scheduled job
	# processes the sensor input from the MCU
	mcu_utils.read_mcu()
