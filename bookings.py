import datetime
import dtutils
import logging
import time
from app import db, models
from config import UNNAMED_MEETING_NAME
from dtutils import MINS_IN_HOUR
from dtutils import SECONDS_IN_MIN
from dtutils import DAY_IN_MINS
from sqlalchemy import text

FIRST_SLOT_START = 8 * MINS_IN_HOUR
LAST_SLOT_START = 18 * MINS_IN_HOUR
MIN_SLOT_DURATION = 15
MORNING = {'start':FIRST_SLOT_START, 'end':12 * MINS_IN_HOUR}
LUNCHTIME = {'start':11 * MINS_IN_HOUR + 30, 'end':13 * MINS_IN_HOUR + 30}
AFTERNOON = {'start':12 * MINS_IN_HOUR, 'end':LAST_SLOT_START}
REMINDER_MINS_BEFORE = 15
REMINDER_MSG = "<@%s> '%s' is starting in %d minutes. See you there!"
REMINDER_MSG_UNNAMED = '<@%s> You have a meeting starting in %d minutes. See you there!'

# All dates and times are UTC

class Slot:
	min_duration = MIN_SLOT_DURATION
	
	def __init__(self, start):
		self.start = start
		self.end = DAY_IN_MINS
		self.duration = -1
		self.ref = None
		self.booking = None
		self.complete = 0
	
	def setEnd(self, end, alt_start, min_slot):
		# convenience method, resets the slot start if the slot duration is too short
		if end - self.start < min_slot:
			self.start = alt_start
		else:
			self.end = end
			self.duration = self.end - self.start
			self.complete = 1
	
	def setDate(self, date):
		# optional date
		self.date = date

	def isComplete(self):
		return self.complete


def align_booking_start(tod_in_mins):
	# align slot/booking start is the next 15 min boundary
	diff = tod_in_mins % 15
	if diff == 0:
		return tod_in_mins
	
	return tod_in_mins + 15 - diff


def remove_unconfirmed_bookings(booker_sid):
	# delete any previous suggestions
	models.UnconfirmedBooking.query. \
		filter(models.UnconfirmedBooking.booker_sid == booker_sid).delete()
	db.session.commit()
	logging.debug('Deleted any remaining unconfirmed booking(s) for %s', booker_sid)


BOOKING_FILTER_STMT = text('start_date=:now_date and start_time + duration >= :now_tod')

def available_slots(day, tod_in_mins, min_duration, booker_sid=None, clean_ucbookings=True):
	# create a list of times when the room is currently available
	
	# remove any existing unconfirmed bookings, for the specified user
	if clean_ucbookings and booker_sid:
		remove_unconfirmed_bookings(booker_sid)
	
	# get a list of existing bookings
	slot_start = align_booking_start(tod_in_mins)
	bookings = models.ConfirmedBooking.query.filter(BOOKING_FILTER_STMT).\
		params(now_date=day.date(), now_tod=slot_start).order_by('start_time').all()

	# get a list of available slots, e.g. unbooked times
	slots = []
	index = -1
	for booking in bookings:
		logging.debug('booking: %s', booking)

		end_time = booking.start_time + booking.duration
		# first slot
		if index== -1:
			# the first booking in the list may have started in the past
			if booking.start_time < slot_start:
				slots.append(Slot(end_time))
				index = 0
				continue
			else:
				slots.append(Slot(slot_start))
				index = 0
		# existing slot, ending at the start of this booking
		# unless the slot duration is less than the min duration
		# in which case set slot to start at the end of this booking
		slots[index].setEnd(booking.start_time, end_time, min_duration)
		
		# new slot, starting at the end of this booking
		if slots[index].isComplete():
			slots.append(Slot(end_time))
			index += 1	

	logging.debug('index: %d', index)

	# nothing in the db, so room is free for the rest of the day
	no_bookings = False
	if index == -1:
		slot = Slot(slot_start)
		slot.setEnd(DAY_IN_MINS, 0, min_duration)
		slots = [slot]
		no_bookings = True

	# an incomplete slot could indicate that the last slot ends at midnight
	# or it could indicates that the room is fully booked
	if index >= 0 and not slots[index].isComplete():
		# set the slot to end at midnight
		slots[index].setEnd(DAY_IN_MINS, 0, min_duration)
		
		# if the slot is too short, remove it
		if not slots[index].isComplete():
			del slots[index]
			index -= 1

	return slots, no_bookings


def suggest_slots(avail_slots, req_duration):
	# create a list of up to 4 booking suggestions
	suggested_slots = []
	for avail_slot in avail_slots:
		if avail_slot.start > LAST_SLOT_START:
			logging.debug('Break: avail_slot.start > LAST_SLOT_START')
			break

		# a slot that's req_duration mins long
		if avail_slot.duration >= req_duration:
			suggested_slot = Slot(avail_slot.start)
			suggested_slot.setEnd(suggested_slot.start + req_duration, 0, req_duration)
			suggested_slots.append(suggested_slot)
			logging.debug('Added: suggested_slot(%d, %d, %d)' 
				% (suggested_slot.start, suggested_slot.end, suggested_slot.duration))
			if len(suggested_slots) == 4:
				break

			# a slot that's req_duration x 2 mins long
			if avail_slot.duration >= req_duration * 2:
				suggested_slot = Slot(avail_slot.start)
				suggested_slot.setEnd(suggested_slot.start + req_duration * 2, 0, req_duration * 2)
				suggested_slots.append(suggested_slot)
				logging.debug('Added: suggested_slot(%d, %d, %d)' 
					% (suggested_slot.start, suggested_slot.end, suggested_slot.duration))
				if len(suggested_slots) == 4:
					break

			# a slot that's 1 hour later and that's req_duration mins long
			if avail_slot.duration >= req_duration + MINS_IN_HOUR \
				and avail_slot.start + MINS_IN_HOUR <= LAST_SLOT_START:
				suggested_slot = Slot(avail_slot.start + MINS_IN_HOUR)
				suggested_slot.setEnd(suggested_slot.start + req_duration, 0, req_duration)
				suggested_slots.append(suggested_slot)
				logging.debug('Added: suggested_slot(%d, %d, %d)' 
					% (suggested_slot.start, suggested_slot.end, suggested_slot.duration))
				if len(suggested_slots) == 4:
					break

			# a slot that's 2 hours later and that's req_duration mins long
			if avail_slot.duration >= req_duration + MINS_IN_HOUR * 2 \
				and avail_slot.start + MINS_IN_HOUR * 2 <= LAST_SLOT_START:
				suggested_slot = Slot(avail_slot.start + MINS_IN_HOUR * 2)
				suggested_slot.setEnd(suggested_slot.start + req_duration, 0, req_duration)
				suggested_slots.append(suggested_slot)
				logging.debug('Added: suggested_slot(%d, %d, %d)' 
					% (suggested_slot.start, suggested_slot.end, suggested_slot.duration))
				if len(suggested_slots) == 4:
					break

		# a slot that's at least {min_duration} mins duration
		elif req_duration >= Slot.min_duration * 2 and avail_slot.duration >= req_duration / 2:
			suggested_slot = Slot(avail_slot.start)
			suggested_slot.setEnd(suggested_slot.start + avail_slot.duration, 0, req_duration / 2)
			suggested_slots.append(suggested_slot)
			logging.debug('Added: suggested_slot(%d, %d, %d)' 
				% (suggested_slot.start, suggested_slot.end, suggested_slot.duration))
			if len(suggested_slots) == 4:
				break

	return suggested_slots


def create_unconfirmed_booking(day, slot, booker_sid):
	# store a booking suggestion
	ucbooking = models.UnconfirmedBooking(start_date=day.date(), start_time=slot.start, 
				duration=slot.duration, booker_sid=booker_sid, booker_ref=slot.ref)
	db.session.add(ucbooking)
	db.session.commit()


def confirm_booking(booker_sid, booker_ref, attendees, name=None,
	set_reminder=False, slack_channel=None):
	# convert a booking suggestion into a booking
	
	# fetch the booking that is being confirmed
	ucbooking = models.UnconfirmedBooking.query.filter( \
		models.UnconfirmedBooking.booker_sid == booker_sid,
		models.UnconfirmedBooking.booker_ref == booker_ref).first()
	if ucbooking:
		logging.debug('ucbooking: %s', ucbooking)
	
		if ucbooking.start_date and ucbooking.start_time and ucbooking.duration:
			if ucbooking.attendees == None:
				if attendees:
					ucbooking.attendees = attendees
				else:
					ucbooking.attendees = 1
			logging.debug('ucbooking.attendees: %d', ucbooking.attendees)
			
			reminder_text = None
			if name == None:
				name=UNNAMED_MEETING_NAME
				if set_reminder:
					reminder_text = REMINDER_MSG_UNNAMED % (booker_sid, REMINDER_MINS_BEFORE)
			elif set_reminder:
				reminder_text = REMINDER_MSG % (booker_sid, name, REMINDER_MINS_BEFORE)
		
			# create the booking
			booking = models.ConfirmedBooking(start_date=ucbooking.start_date,
				start_time=ucbooking.start_time, duration=ucbooking.duration,
				booker_sid=ucbooking.booker_sid, attendees=ucbooking.attendees,
				name=name)
			db.session.add(booking)
			db.session.commit()
			logging.debug('Created confirmed booking for %s', booker_sid)

			# remove any remaining booking suggestions
			remove_unconfirmed_bookings(booker_sid)
			
			# add a reminder
			if set_reminder and slack_channel:
				# fetch the booking we just saved, so we have the id
				booking = models.ConfirmedBooking.query.filter( \
					models.ConfirmedBooking.start_date == booking.start_date,
					models.ConfirmedBooking.start_time == booking.start_time).first()
				
				if booking:					
					# create the reminder
					t = datetime.time(hour=int(booking.start_time / MINS_IN_HOUR),
						minute=booking.start_time % MINS_IN_HOUR)
					send_at = dtutils.to_timestamp( \
						dtutils.convert_date_to_datetime(booking.start_date, t))
					send_at -= REMINDER_MINS_BEFORE * SECONDS_IN_MIN
					if send_at > time.time():
						reminder = models.Reminder(send_at=send_at, booking=booking.id,
							slack_channel=slack_channel, text=reminder_text)
						db.session.add(reminder)
						db.session.commit()
						logging.debug('Created reminder for booking %d', booking.id)
		
			return booking
	
	return None

BOOKING_ORDER_BY_STMT = text(('start_date, start_time'))

def get_bookings(booker_sid, dt=None):
	# create a list of bookings for the specified booker_sid
	if dt == None:
		dt = dtutils.local_datetime_now()
	query_date = dt.date()
	
	bookings = []
	if booker_sid:
		bookings = models.ConfirmedBooking.query.filter( \
			models.ConfirmedBooking.start_date >=  query_date, 
			models.ConfirmedBooking.booker_sid == booker_sid). \
			order_by(BOOKING_ORDER_BY_STMT).all()				
	else:
		bookings = models.ConfirmedBooking.query.filter( \
			models.ConfirmedBooking.start_date >=  query_date). \
			order_by(BOOKING_ORDER_BY_STMT).all()				
		
	slots = []
	for booking in bookings:
		slot = Slot(booking.start_time)
		slot.setEnd(booking.start_time + booking.duration, 0, MIN_SLOT_DURATION)
		slot.setDate(booking.start_date)
		slot.booking = booking
		slots.append(slot)

	# remove any slots from before now, too messy to do in db given the small number
	tod_in_mins = dt.hour * 60 + dt.minute
	slots = [s for s in slots if not (s.date == query_date and s.end < tod_in_mins)]

	return slots


def remove_booking_refs(booker_sid):
	# remove old references used by commands such as show and name
	models.ConfirmedBookingRef.query. \
		filter(models.ConfirmedBookingRef.booker_sid == booker_sid).delete()
	db.session.commit()
	logging.debug('Deleted any remaining booking ref(s) for %s', booker_sid)


def set_booking_refs(booker_sid, slots):
	# remove any existing booking refs
	remove_booking_refs(booker_sid)
	
	for slot in slots:
		ref = models.ConfirmedBookingRef(booker_sid=slot.booking.booker_sid, booker_ref=slot.ref,
			booking=slot.booking.id)
		db.session.add(ref)
	db.session.commit()


def get_booking_by_ref(booker_sid, booker_ref):
	# fetch the booking indicated by the specified reference
	ref = models.ConfirmedBookingRef.query.filter( \
		models.ConfirmedBookingRef.booker_sid == booker_sid,
		models.ConfirmedBookingRef.booker_ref == booker_ref).first()
	if ref:
		return models.ConfirmedBooking.query.get(ref.booking)

	return None
	

def update_booking_by_ref(booker_sid, booker_ref, name=None):
	# fetch the booking indicated by the specified reference
	if name:
		booking = get_booking_by_ref(booker_sid, booker_ref)
		if booking:
			booking.name = name
			db.session.add(booking)
			db.session.commit()
			return booking
		
	return None
	
