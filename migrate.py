import logging
import random
import string

import webapp2

from models import Event
from notices import *

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def generate_wifi_password():
    num = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return num


class MigrateHandler(webapp2.RequestHandler):
    """
    Handler to migrate data to new scheme

    """
    def get(self):
        events = Event.get_approved_list_with_multiday()
        logger.debug(events)

        for event in events:
            logger.debug(event)
            if event.wifi_password == "":
                logger.debug("Adding wifi password for Event %s" % event.name)
                event.wifi_password = generate_wifi_password()
                event.put()
                notify_wifi_password_added(event)
            else:
                logger.info("Wifi password present for Event %s" % event.name)

app = webapp2.WSGIApplication([
    ('/migrate/wifi', MigrateHandler),
], debug=True)
