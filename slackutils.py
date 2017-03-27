import datetime
import dtutils
import logging
from app import slack_client
from config import BOT_ID

MESSAGE_EVENT_TYPE = 'message'
USER_CHG_EVENT_TYPE = 'user_change'

def format_slack_date(dt):
	# create a correctly formated date, ready for sending to slack
	s = dt.strftime('%b %d, %Y')
	return '<!date^%d^{date_long_pretty}|%s>' % (dtutils.to_timestamp(dt), s)


def format_slack_time(day_ts, tod_in_mins):
	# create a correctly formated time, ready for sending to slack
	return '<!date^%d^{time}|%02d:%02d>' % \
		(day_ts + tod_in_mins * 60, tod_in_mins / 60, tod_in_mins % 60)


def filter_slack_events(slack_rtm_events):
	# the slack Real Time Messaging API is firehose of events
	# this function looks for messages directed at the bot, based on its id
	event_list = slack_rtm_events
	if event_list and len(event_list) > 0:
		logging.info('Received slack RTM event(s): %s', event_list)
		for event in event_list:
			#process message event
			if event and 'type' in event:
				# message events which include the bot
				if event['type'] == MESSAGE_EVENT_TYPE and 'text' in event \
					and event['text'].find(BOT_ID) != -1:
					return {'type':MESSAGE_EVENT_TYPE, 
						'channel':event['channel'],
						'user':event['user'],
						'message':event['text']}

	return None


def get_slack_user(id):
	# fetches selected user.info data from slack
	result = slack_client.api_call("users.info", user=id)
	if result['ok']:
		user = result['user']
		if user['deleted'] == False and user['is_bot'] == False:
			profile = user['profile']
			return {'id':user['id'], 'name':user['name'],
				'real_name':profile['real_name'], 'image_48':profile['image_48']}
		
		logging.info('user: %s; deleted: %s; is_bot: %s' % \
			(id, user['deleted'], user['is_bot']))
	
	return None