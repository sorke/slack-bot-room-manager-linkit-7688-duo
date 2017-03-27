from app import db

class ConfirmedBooking(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	start_date = db.Column(db.Date, index=True, nullable=False)
	start_time = db.Column(db.Integer, index=True, nullable=False)
	duration = db.Column(db.Integer, nullable=False)
	booker_sid = db.Column(db.String(10), db.ForeignKey('slack_user.sid'), nullable=False)
	attendees = db.Column(db.Integer, nullable=False)
	attendee_sids = db.Column(db.Text, nullable=True)
	in_progress = db.Column(db.Boolean, default=False)
	finished = db.Column(db.Boolean, index=True, default=False)
	name = db.Column(db.String(40), nullable=True)

	def __repr__(self):
		state = 'no started'
		if self.finished:
			state = 'finished'
		elif self.in_progress:
			state = 'in progress'
		
		return '<ConfirmedBooking %r %d %d %s %s>' % \
			(self.start_date, self.start_time, self.duration, self.booker_sid, state)


class Reminder(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	send_at = db.Column(db.Integer, index=True, nullable=False)
	slack_channel = db.Column(db.String(10), nullable=False)
	text = db.Column(db.Text, nullable=False)
	booking = db.Column(db.Integer, db.ForeignKey('confirmed_booking.id'), nullable=False)

	def __repr__(self):
		return '<Reminder %d %s>' % (self.send_at, self.text)


class SlackUser(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	sid = db.Column(db.String(10), nullable=False, unique=True)
	name = db.Column(db.String(64), nullable=False)
	real_name = db.Column(db.String(64), nullable=True)
	image_48 = db.Column(db.String(100), nullable=True)
	bookings = db.relationship('ConfirmedBooking', backref='booker', lazy='dynamic')

	def __repr__(self):
		return '<SlackUser %s %s>' % (self.sid, self.name)


class UnconfirmedBooking(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	start_date = db.Column(db.Date, nullable=False)
	start_time = db.Column(db.Integer, nullable=False)
	duration = db.Column(db.Integer, nullable=False)
	booker_sid = db.Column(db.String(10), nullable=False)
	booker_ref = db.Column(db.Integer, nullable=False)
	attendees = db.Column(db.Integer, nullable=True)

	def __repr__(self):		
		return '<UnconfirmedBooking %r %d %d %s>' % \
			(self.start_date, self.start_time, self.duration, self.booker_sid)


class ConfirmedBookingRef(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	booker_sid = db.Column(db.String(10), db.ForeignKey('slack_user.sid'), nullable=False)
	booker_ref = db.Column(db.Integer, nullable=False)
	booking = db.Column(db.Integer, db.ForeignKey('confirmed_booking.id'), nullable=False)

	def __repr__(self):
		return '<ConfirmedBookingRefs %s %d %d>' % \
			(self.booker_sid, self.booker_ref, self.booking)

