""" Tests for the stuff in main.py. """

# This goes at the top so that we have access to all of our external
# dependencies.
import appengine_config

import datetime
import os
import unittest

from google.appengine.dist import use_library
from google.appengine.ext import db
from google.appengine.ext import testbed

import webtest

# This has to go before we import the main module so that the correct settings
# get loaded.
os.environ["DJANGO_SETTINGS_MODULE"] = "settings"

import main
import models


""" A base class for the tests in this file that deals with testbed and webtest
boilerplate, among other things. """
class BaseTest(unittest.TestCase):
  """ Checks that the correct datastore entries got created for a new event.
  params: An optional set of parameters to check the event against. (Otherwise,
  self.params will be used.) """
  def _check_new_event_in_datastore(self, params=None):
    if not params:
      params = self.params

    # Check that the event was created.
    pending = models.Event.get_pending_list().get()
    self.assertEqual(params["name"], pending.name)
    # Check that it was logged.
    log = models.HDLog().all().get()
    self.assertEqual(params["name"], log.event.name)

  def setUp(self):
    # Set up GAE testbed.
    self.testbed = testbed.Testbed()
    self.testbed.activate()

    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_taskqueue_stub()

    # Set up testing for application.
    self.test_app = webtest.TestApp(main.app)

    # Simulate a logged-in user.
    self.testbed.setup_env(user_email="testy.testerson@gmail.com",
                           user_is_admin="0", overwrite=True)

    # Default parameters for putting in the form.
    date = datetime.date.today()
    event_date = "%d/%d/%d" % (date.month, date.day + 1, date.year)
    self.params = {"start_date": event_date,
                   "start_time_hour": "12",
                   "start_time_minute": "0",
                   "start_time_ampm": "PM",
                   "end_date": event_date,
                   "end_time_hour": "2",
                   "end_time_minute": "0",
                   "end_time_ampm": "PM",
                   "setup": "15",
                   "teardown": "15",
                   "rooms": "Classroom",
                   "details": "This is a test event.",
                   "estimated_size": "10",
                   "name": "Test Event",
                   "type": "Meetup",
                  }

""" Tests that the new event handler works properly. """
class NewHandlerTest(BaseTest):
  """ Tests that it gives us a page that seems correct. """
  def test_get(self):
    response = self.test_app.get("/new")
    self.assertEqual(200, response.status_int)

    self.assertIn("New Event", response.body)

  """ Tests that we can actually create a new event. """
  def test_post(self):
    response = self.test_app.post("/new", self.params)
    self.assertEqual(200, response.status_int)

    self._check_new_event_in_datastore()

  """ Tests that it properly requires members hosting long events to specify the
  name of another member. """
  def test_second_member_requirement(self):
    params = self.params.copy()
    date = datetime.date.today()
    # Make it last 24 hours or more.
    params["end_date"] = "%d/%d/%d" % (date.month, date.day + 2, date.year)

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    # It should give us an error about specifying the email address.
    self.assertIn("specify second", response.body)

    # If we enter one, it should let us create it.
    params["other_member"] = "other.member.test@gmail.com"
    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    self._check_new_event_in_datastore()


""" Tests that the edit event handler works properly. """
class EditHandlerTest(BaseTest):
  def setUp(self):
    super(EditHandlerTest, self).setUp()

    # Make an event for us to edit.
    event_start = datetime.datetime.now() + datetime.timedelta(days=1)
    event_end = datetime.datetime.now() + datetime.timedelta(days=1, hours=2)
    self.event = models.Event(name="Test Event", start_time=event_start,
                              end_time=event_end, type="Meetup",
                              estimated_size="10", setup=15, teardown=15,
                              details="This is a test event.")
    self.event.put()

  """ Tests that it gives us a page that seems correct. """
  def test_get(self):
    response = self.test_app.get("/event/%d" % (self.event.key().id()))
    self.assertEqual(200, response.status_int)

  """ Tests that we can reasonably edit the event. """
  def test_post(self):
    response = self.test_app.post("/edit/%d" % (self.event.key().id()),
                                  self.params)
    self.assertEqual(200, response.status_int)

    # The event should still be in the datastore.
    self._check_new_event_in_datastore()

    # Try changing the name now.
    params = self.params.copy()
    params["name"] = "New Test Event"

    response = self.test_app.post("/edit/%d" % (self.event.key().id()), params)
    self.assertEqual(200, response.status_int)

    self._check_new_event_in_datastore(params=params)

  """ Tests that it properly requires members hosting long events to specify the
  name of another member. """
  def test_second_member_requirement(self):
    params = self.params.copy()
    date = datetime.date.today()
    # Make it last 24 hours or more.
    params["end_date"] = "%d/%d/%d" % (date.month, date.day + 2, date.year)

    response = self.test_app.post("/edit/%d" % (self.event.key().id()), params,
                                  expect_errors=True)
    self.assertEqual(400, response.status_int)

    # It should give us an error about specifying the email address.
    self.assertIn("specify second", response.body)

    # If we enter one, it should let us create it.
    params["other_member"] = "other.member.test@gmail.com"
    response = self.test_app.post("/edit/%d" % (self.event.key().id()), params)
    self.assertEqual(200, response.status_int)

    self._check_new_event_in_datastore()

