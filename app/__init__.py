import logging
import os
from flask import Flask
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy
from PyMata.pymata import PyMata
from slackclient import SlackClient

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s (%(threadName)-10s) %(message)s',
                    )

app = Flask(__name__)
app.config.from_object('config')

# instantiate db before scheduler, as it is a dependency for some jobs
db = SQLAlchemy(app)

# instantiate slack_client before scheduler, as it is a dependency for some jobs
slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))

# instantiate PyMata interface to the MCU (ATmega32U4)
mcu = PyMata("/dev/ttyS0", verbose=True)

# instantiate the scheduler
scheduler = APScheduler()
scheduler.init_app(app)

from app import views, models
