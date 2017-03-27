import os
from pytz import utc

basedir = os.path.abspath(os.path.dirname(__file__))

# slack related
BOT_ID = os.environ.get("BOT_ID")

# db related
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')
SQLALCHEMY_TRACK_MODIFICATIONS=True

# scheduler related
JOBS = [
	{
		'id': 'job1',
		'replace_existing': True,
		'func': 'jobs:read_slack_rtm',
		'trigger': 'interval',
		'seconds': 2,
		'coalesce': True
	},
	{
		'id': 'job2',
		'replace_existing': True,
		'func': 'jobs:send_reminders',
		'trigger': 'cron',
		'minute': '*/15',
		'coalesce': True
	},
	{
		'id': 'job3',
		'replace_existing': True,
		'func': 'jobs:cleanup_bookings',
		'trigger': 'cron',
		'hour': 3,
		'coalesce': True
	},
	{
		'id': 'job4',
		'replace_existing': True,
		'func': 'jobs:mcu_handler',
		'trigger': 'interval',
		'seconds': 30,
		'coalesce': True
	}

]

SCHEDULER_EXECUTORS = {
    'default': {'type': 'threadpool', 'max_workers': 2}
}

SCHEDULER_TIMEZONE = utc

SCHEDULER_API_ENABLED = False

# web form related
WTF_CSRF_ENABLED = True
SECRET_KEY = 'you-will-never-guess'

# PyMata related

# digital pins
ELECTRICITY_RELAY = 9
MOTION_SENSOR = 8

# analog pins
ELECTRICITY_SENSOR = 2
TEMP_SENSOR = 1
LIGHT_SENSOR = 0

# controls when the ELECTRICITY_RELAY is activated (closed)
LIGHT_SENSOR_THRESHOLD = {'low':490, 'high':650}

# controls when messages are sent to room bookers
TEMP_SENSOR_THRESHOLD = {'low':18, 'high':25}

# misc
LOW_TEMP_MESSAGE = "I'm a bit chilly! So you might want to being a sweater"
HIGH_TEMP_MESSAGE = "I'm hot! So you might want to being a sweater"

UNNAMED_MEETING_NAME = 'Unnamed Meeting'