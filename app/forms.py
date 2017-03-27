from flask_wtf import FlaskForm
from wtforms import HiddenField
from wtforms.validators import DataRequired

class RoomDisplayForm(FlaskForm):
    booking_id = HiddenField('booking_id', validators=[DataRequired()])
    action = HiddenField('action', validators=[DataRequired()])
