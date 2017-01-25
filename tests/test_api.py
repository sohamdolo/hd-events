""" Tests for api.py. """


# We need our externals.
import appengine_config

import datetime
import unittest

from google.appengine.api import users
from google.appengine.ext import db, testbed

import webtest

from models import Event
import api


""" A base class for the tests in this file that deals with testbed and webtest
boilerplate, among other things. """
class BaseTest(unittest.TestCase):
  def setUp(self):
    # Set up GAE testbed.
    self.testbed = testbed.Testbed()
    self.testbed.activate()

    self.testbed.init_datastore_v3_stub()

    # Set up testing for application.
    self.test_app = webtest.TestApp(api.app)

    # Default parameters for the API request.
    self.params = {"username": "testy.testerson", "status": "suspended"}


""" Tests for the StatusChangeHandler. """
class StatusChangeHandlerTest(BaseTest):
  def setUp(self):
    super(StatusChangeHandlerTest, self).setUp()

    # Make an event from a specific user.
    start = datetime.datetime.now() + datetime.timedelta(days=1)
    user = users.User(email="testy.testerson@hackerdojo.com")
    event = Event(member=user, status="pending", start_time=start,
                  type="Meetup", estimated_size="10", name="Test Event",
                  details="test")
    event.put()

    self.event_id = event.key().id()

  """ Gets the most recent log pertaining to this event.
  Args:
    event: The event that we want logs pertaining to. """
  def __get_latest_log(self, event):
    return db.GqlQuery("SELECT * FROM HDLog WHERE event = :1 \
                        ORDER BY created DESC", event).get()

  """ Tests that it correctly puts the event on hold and restores it. """
  def test_hold_and_restore(self):
    # Put the event on hold.
    response = self.test_app.post("/api/v1/status_change", self.params)
    self.assertEqual(200, response.status_int)

    event = Event.get_by_id(self.event_id)
    self.assertEqual("suspended", event.status)
    self.assertNotEqual(None, event.owner_suspended_time)
    self.assertEqual("pending", event.original_status)

    # Check that it was logged.
    log_event = self.__get_latest_log(event)
    self.assertIn("Suspended event", log_event.description)

    # Restore the event.
    params = self.params.copy()
    params["status"] = "active"
    response = self.test_app.post("/api/v1/status_change", params)
    self.assertEqual(200, response.status_int)

    event = Event.get_by_id(self.event_id)
    self.assertEqual("pending", event.status)
    self.assertEqual(None, event.owner_suspended_time)
    self.assertEqual(None, event.original_status)

    log_event = self.__get_latest_log(event)
    self.assertIn("Restoring event", log_event.description)

  """ Tests that it ignores certain status changes. """
  def test_ignore_status(self):
    params = self.params.copy()
    params["status"] = "no_visits"
    response = self.test_app.post("/api/v1/status_change", params)
    self.assertEqual(200, response.status_int)

    event = Event.get_by_id(self.event_id)
    self.assertEqual("pending", event.status)
    self.assertEqual(None, event.owner_suspended_time)
    self.assertEqual(None, event.original_status)
