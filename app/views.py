import bookings
import datetime
import dtutils
import logging
import math
from app import app, db, models
from config import UNNAMED_MEETING_NAME
from dtutils import MINS_IN_HOUR
from flask import render_template, redirect
from .forms import RoomDisplayForm
from sqlalchemy import text

FILTER_STMT = text('finished=0 and start_date=:now_date and start_time + duration >= :now_tod')

CTA_NEW_BOOKING = {'cta':'Meet Now', 'action':1}
CTA_START_MEETING = {'cta':'Start Meeting', 'action':2}
CTA_START_MEETING_EARLY = {'cta':'Start Meeting Early', 'action':2}
CTA_END_MEETING = {'cta':'End Meeting', 'action':3}
CTA_STEAL_AND_BOOK = {'cta':'Steal Me', 'action':4}

MSG_AVAILABLE = 'Available'
MSG_BOOKING_STARTS_SOON = '%s'
MSG_BOOKING_WAITING = '%s'
MSG_BOOKING_IN_PROGRESS = '%s'
MSG_BOOKING_ABANDONED = '%s, abandoned'
MSG_NO_BOOKINGS_ROTD = "I'm free for the rest of the day"
MSG_CURR_BOOKING_ENDS = 'The current meeting ends in %d minutes, at %02d:%02d'
MSG_NEXT_BOOKING_STARTS = 'The next meeting starts in %d %s'
MSG_CHECK_SLACK = 'Check upcoming meetings on Slack:'
MSG_NEXT_FREE_AT = "I'm next free at %02d:%02d for %d minutes"
MSG_FREE_ROTD_AFTER = 'After %02d:%02d, ' + MSG_NO_BOOKINGS_ROTD

ROOM = {'id':'@room1d', 'name':'Room 1D', 'type':'Conference Room'}

DEFAULT_MEETING_NAME = 'Impromptu Meeting'


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
	now = dtutils.local_datetime_now()
	now_date = now.date()
	now_tod = now.hour * MINS_IN_HOUR + now.minute
	logging.debug('now_date: %s; now_tod: %d' % (now_date, now_tod))

	booking_id = -1
	cta = CTA_NEW_BOOKING
	form = RoomDisplayForm(booking_id=booking_id,action=cta['action'])
	if form.validate_on_submit():
		logging.debug('form.validate_on_submit() - booking_id.data: %s; action.data: %s' \
			% (form.booking_id.data, form.action.data))

		if int(form.action.data) == CTA_NEW_BOOKING['action'] or \
			int(form.action.data) == CTA_STEAL_AND_BOOK['action']:
			logging.debug('CTA_NEW_BOOKING or CTA_STEAL_AND_BOOK')

			if int(form.action.data) == CTA_STEAL_AND_BOOK['action']:
				logging.debug('CTA_STEAL_AND_BOOK')
				# delete booking
				models.ConfirmedBooking.query.filter_by(id = int(form.booking_id.data)).delete()
			
			b = models.ConfirmedBooking(start_date=now_date,
				start_time=bookings.align_booking_start(now_tod), duration=30,
				booker_sid='DWALKIN', attendees=1, name=DEFAULT_MEETING_NAME)
			db.session.add(b)
			db.session.commit()
		elif int(form.action.data) == CTA_START_MEETING['action'] or \
			int(form.action.data) == CTA_START_MEETING_EARLY['action']:
			logging.debug('CTA_START_MEETING or CTA_START_MEETING_EARLY')
			b = models.ConfirmedBooking.query.get(int(form.booking_id.data))
			if b:
				b.in_progress = True
				db.session.add(b)
				db.session.commit()
		elif int(form.action.data) == CTA_END_MEETING['action']:
			logging.debug('CTA_END_MEETING')
			b = models.ConfirmedBooking.query.get(int(form.booking_id.data))
			if b:
				b.in_progress = False
				b.finished = True
				db.session.add(b)
				db.session.commit()

		return redirect('/index')
	
	conf_bookings = models.ConfirmedBooking.query.filter(FILTER_STMT).\
		params(now_date=now_date, now_tod=now_tod).order_by('start_time').limit(2).all()
	
	colour = 'success'
	availability = MSG_AVAILABLE
	current_booking = None
	next_booking = None
	next_free = None
	for b in conf_bookings:
		if next_free == None:
			# the end of the first meeting in the list
			next_free = [b.start_time + b.duration]
		elif b.start_time == next_free[0]:
			# the end of the last meeting in the list
			next_free[0] = b.start_time + b.duration
		else:
			next_free.append(b.start_time)

		if b.in_progress:
			current_booking = b
			colour = 'danger'
			availability = MSG_BOOKING_IN_PROGRESS
			booking_id = b.id
			cta = CTA_END_MEETING
		elif b.start_time <= now_tod:
			current_booking = b
			colour = 'warning'
			booking_id = b.id
			if b.start_time <= now_tod - 10:
				availability = MSG_BOOKING_ABANDONED
				cta = CTA_STEAL_AND_BOOK
			else:
				availability = MSG_BOOKING_WAITING
				cta = CTA_START_MEETING
		else:
			# the first future booking is the next booking
			if next_booking == None:
				next_booking = b
			if now_tod + 15 > b.start_time and availability == MSG_AVAILABLE:
				colour = 'warning'
				availability = MSG_BOOKING_STARTS_SOON
				booking_id = b.id
				cta = CTA_START_MEETING_EARLY

	booker = None
	if availability.startswith('%s'):
		if current_booking:
			if current_booking.name:
				availability = availability % (current_booking.name)
				booker = current_booking.booker
		elif next_booking:
			if next_booking.name:
				availability = availability % (next_booking.name)
				booker = next_booking.booker
		else:
			availability = availability % (UNNAMED_MEETING_NAME)
	
	next_free_msg = MSG_NO_BOOKINGS_ROTD
	if next_free and len(next_free) == 1 and len(conf_bookings) == 2:
		# could be the last booking of the day or just the last booking in the list
		next_free_msg = MSG_CHECK_SLACK
	elif next_free and len(next_free) == 2:
		next_free_msg = MSG_NEXT_FREE_AT % \
			(next_free[0] // MINS_IN_HOUR, next_free[0] % MINS_IN_HOUR, \
			next_free[1] - next_free[0])
	elif current_booking:
		booking_ends = current_booking.start_time + current_booking.duration
		next_free_msg = MSG_FREE_ROTD_AFTER % \
			(booking_ends // MINS_IN_HOUR, booking_ends % MINS_IN_HOUR)
	elif next_booking:
		booking_ends = next_booking.start_time + next_booking.duration
		next_free_msg = MSG_FREE_ROTD_AFTER % \
			(booking_ends // MINS_IN_HOUR, booking_ends % MINS_IN_HOUR)
	
	next_booking_msg = MSG_NO_BOOKINGS_ROTD
	if next_booking == None:
		if current_booking:
			booking_ends = current_booking.start_time + current_booking.duration
			num_mins = booking_ends - now_tod
			next_booking_msg = MSG_CURR_BOOKING_ENDS % \
				(num_mins, booking_ends // MINS_IN_HOUR, booking_ends % MINS_IN_HOUR)
	else:
		msg = MSG_NEXT_BOOKING_STARTS
		num_mins = next_booking.start_time - now_tod
		if num_mins > 90:
			msg = msg % (int(math.ceil(num_mins / MINS_IN_HOUR)), 'hours')
		else:
			msg = msg % (num_mins, 'minutes')
		next_booking_msg = msg + ', at %02d:%02d' % \
			(next_booking.start_time // MINS_IN_HOUR, next_booking.start_time % MINS_IN_HOUR)
		
	form = RoomDisplayForm(booking_id=booking_id,action=cta['action'])
	status = {'colour':colour, 'availability':availability, 'next_free':next_free_msg,
		'next_booking':next_booking_msg, 'cta':cta['cta'], 'booker':booker}
	time = '%02d:%02d' % (now.hour, now.minute)
	return render_template('index.html', room=ROOM, status=status, form=form)
