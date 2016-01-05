""" Tests for the stuff in main.py. """


# This goes at the top so that we have access to all of our external
# dependencies.
import appengine_config

import datetime
import json
import os
import unittest

from google.appengine.dist import use_library
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import testbed

import webtest

# This has to go before we import the main module so that the correct settings
# get loaded.
os.environ["DJANGO_SETTINGS_MODULE"] = "settings"

from config import Config
from models import Event
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

  """ Creates a series of events in the datastore for testing purposes. Each
  event is an hour long and separated from the next event by exactly one day.
  The first event defaults to being made exactly one day in the future from the
  current time.
  events: How many events to create.
  offset: Specify how many days beyond the current day to create the first
  event.
  Returns: A list of the events created. """
  def _make_events(self, events, offset=1):
    start = datetime.datetime.now() + datetime.timedelta(days=offset)
    made_events = []
    for i in range(0, events):
      event = models.Event(name="Test Event", start_time=start,
                           end_time=start + datetime.timedelta(hours=1),
                           type="Meetup", estimated_size="10", setup=15,
                           teardown=15, details="This is a test event.")
      event.put()
      made_events.append(event)

    return made_events

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
    date = datetime.date.today() + datetime.timedelta(days=1)
    event_date = "%d/%d/%d" % (date.month, date.day, date.year)
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

    # Make a fake dictionary detailing a basic recurring event.
    self.recurring_data = {"frequency": "monthly", "repetitions": 5,
                           "dayNumber": "1st", "monthDay": "Monday",
                           "weekdaysOnly": False}


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

  """ Tests that it handles missing event names and details correctly. """
  def test_no_name_or_details(self):
    # No name.
    params = self.params.copy()
    params["name"] = ""

    # It should give us an error.
    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("name is required", response.body)

    # No details.
    params = self.params.copy()
    params["details"] = ""

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("details are required", response.body)

  """ Tests that it properly requires members hosting long events to specify the
  name of another member. """
  def test_second_member_requirement(self):
    params = self.params.copy()
    date = datetime.date.today() +  datetime.timedelta(days=2)
    # Make it last 24 hours or more.
    params["end_date"] = "%d/%d/%d" % (date.month, date.day, date.year)

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    # It should give us an error about specifying the email address.
    self.assertIn("specify second", response.body)

    # If we enter one, it should let us create it.
    params["other_member"] = "other.member.test@gmail.com"
    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    self._check_new_event_in_datastore()

  """ Tests that it properly limits members to having a fixed number of future
  events scheduled. """
  def test_event_limit(self):
    # Create the maximum number of events.
    self._make_events(Config().USER_MAX_FUTURE_EVENTS, offset=3)

    # Now it should stop us from creating another one.
    response = self.test_app.post("/new", self.params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("future events", response.body)

  """ Tests that it properly limits the number of events members can have in a
  4-week period. """
  def test_four_week_limit(self):
    # Make one fewer than the limit events.
    events = self._make_events(Config().USER_MAX_FOUR_WEEKS - 1)
    # The start time of our last event.
    last_start = datetime.datetime.now() + \
        datetime.timedelta(days=Config().USER_MAX_FOUR_WEEKS)

    # Now, it should let us create a last one.
    event_date = "%d/%d/%d" % (last_start.month, last_start.day,
                               last_start.year)
    params = self.params.copy()
    params["start_date"] = event_date
    params["end_date"] = event_date

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # It should not, however, allow us to create another one.
    last_start += datetime.timedelta(days=1)
    event_date = "%d/%d/%d" % (last_start.month, last_start.day,
                               last_start.year)
    params["start_date"] = event_date
    params["end_date"] = event_date

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("4-week period", response.body)

  """ Tests that it forces people to select at least one room. """
  def test_no_room_prohibition(self):
    params = self.params.copy()
    del params["rooms"]

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("select a room", response.body)

  """ Tests that it limits people to having one event per day starting during
  Dojo hours. """
  def test_one_per_day(self):
    start = datetime.datetime.now() + datetime.timedelta(days=1)
    # For this test to work, the event initially has to be scheduled on a
    # weekday.
    if start.weekday() > 4:
      start += datetime.timedelta(days=2)
    self.assertLess(start.weekday(), 5)

    start = start.replace(hour=11)
    event = models.Event(name="Test Event", start_time=start,
                         end_time=start + datetime.timedelta(minutes=30),
                         type="Meetup", estimated_size="10", setup=15,
                         teardown=15, details="This is a test event.")
    event.put()

    params = self.params.copy()
    params["start_date"] = "%d/%d/%d" % (start.month, start.day, start.year)
    params["end_date"] = params["start_date"]

    # That should be our one event for that day. It should complain if we try to
    # create another one.
    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("coworking hours", response.body)

    # It should ignore the event if it doesn't have the right status.
    event.status = "not_approved"
    event.put()

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # Another status that should trigger it is approved.
    event.status = "approved"
    event.put()

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("coworking hours", response.body)

    # If the event we are making is not during these hours, it should not have a
    # problem.
    new_params = params.copy()
    new_params["start_time_hour"] = "6"
    new_params["end_time_hour"] = "7"
    response = self.test_app.post("/new", new_params)
    self.assertEqual(200, response.status_int)

    # If we schedule it on a weekend, however, we should have no such problems.
    days_to_weekend = 6 - datetime.datetime.today().weekday()
    start = datetime.datetime.now() + datetime.timedelta(days=days_to_weekend)
    self.assertGreater(start.weekday(), 4)

    event.start_time = start
    event.end_time = start + datetime.timedelta(minutes=30)
    event.put()

    params["start_date"] = "%d/%d/%d" % (start.month, start.day, start.year)
    params["end_date"] = params["start_date"]

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

  """ Tests that you can force it to validate the event as a regular member if
  you are an admin. """
  def test_regular_member_validation(self):
    params = self.params.copy()
    self._make_events(Config().USER_MAX_FUTURE_EVENTS)

    # Make sure it doesn't show the box when we're not an admin.
    response = self.test_app.get("/new")
    self.assertEqual(200, response.status_int)
    self.assertNotIn("regular_user", response.body)

    # Login as admin.
    self.testbed.setup_env(user_is_admin="1", overwrite=True)

    # Make sure the box is there.
    response = self.test_app.get("/new")
    self.assertEqual(200, response.status_int)
    self.assertIn("regular_user", response.body)

    # Check the box.
    params["regular_user"] = True

    # It should not let us.
    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    # Make sure it didn't put it in the datastore.
    events = Event.all().count()
    self.assertEqual(Config().USER_MAX_FUTURE_EVENTS, events)

    # If we uncheck the box, it should let us because we are an admin.
    del params["regular_user"]

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # It should have gone in the datastore.
    events = Event.all().count()
    self.assertEqual(Config().USER_MAX_FUTURE_EVENTS + 1, events)

  """ Test that the backend for creating monthly recurring events works. """
  def test_monthly_recurring_events(self):
    params = self.params.copy()
    params["recurring-data"] = json.dumps(self.recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # Check that we ended up with lots of events in the datastore.
    num_events = Event.all().count()
    self.assertEqual(5, num_events)

    used_months = []
    for event in Event.all().run():
      start_diff = event.start_time - datetime.datetime.now()
      if start_diff.days <= 1:
        # Ignore our initial event, because it will not be right.
        continue

      # Should be on a Monday.
      self.assertEqual(0, event.start_time.weekday())
      # None of them should be in the same month.
      self.assertNotIn(event.start_time.month, used_months)
      used_months.append(event.start_time.month)


  """ Test that the backend for creating weekly recurring events works. """
  def test_weekly_recurring_events(self):
    # Make a recurring event that happens every week.
    recurring_data = self.recurring_data.copy()
    params = self.params.copy()
    recurring_data["frequency"] = "weekly"
    params["recurring-data"] = json.dumps(recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # Check the datastore.
    num_events = Event.all().count()
    self.assertEqual(5, num_events)

    query = db.GqlQuery("SELECT * FROM Event ORDER BY start_time ASC")
    last_event = None
    for event in query.run():
      if last_event:
        # They should all be on the same day of the week.
        self.assertEqual(last_event.start_time.weekday(),
                         event.start_time.weekday())
        # They should all be one week from the last one.
        event_diff = event.start_time - last_event.start_time
        self.assertEqual(7, event_diff.days)

      last_event = event

  """ Test that the backend for creating daily recurring events works. """
  def test_daily_recurring_events(self):
    # Make a recurring event that happens every day.
    recurring_data = self.recurring_data.copy()
    params = self.params.copy()
    recurring_data["frequency"] = "daily"
    params["recurring-data"] = json.dumps(recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # Check the datastore.
    num_events = Event.all().count()
    self.assertEqual(5, num_events)

    query = db.GqlQuery("SELECT * FROM Event ORDER BY start_time ASC")
    last_event = None
    for event in query.run():
      if last_event:
        # They should all be one day from the last one.
        event_diff = event.start_time - last_event.start_time
        self.assertEqual(1, event_diff.days)

      last_event = event

  """ Test that the backend for creating daily recurring events excluding
  weekends works. """
  def test_recurring_no_weekends(self):
    # Make a recurring event that happens every day.
    recurring_data = self.recurring_data.copy()
    params = self.params.copy()
    recurring_data["frequency"] = "daily"
    # We want to force there to be some weekends...
    recurring_data["repetitions"] = 6
    recurring_data["weekdaysOnly"] = True
    params["recurring-data"] = json.dumps(recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params)
    self.assertEqual(200, response.status_int)

    # Check the datastore.
    num_events = Event.all().count()
    self.assertEqual(6, num_events)

    query = db.GqlQuery("SELECT * FROM Event ORDER BY start_time ASC")
    last_event = None
    for event in query.run():
      if last_event:
        event_diff = event.start_time - last_event.start_time
        if last_event.start_time.weekday() < 4:
          # They should all be one day from the last one, unless the last one
          # was on Friday or a weekend. (The first one could still be on a
          # weekend.)
          self.assertEqual(1, event_diff.days)

        self.assertLess(event.start_time.weekday(), 5)

      last_event = event

  """ Test that it properly detects trying to add too many events at once. """
  def test_recurring_event_limit(self):
    # Put some initial events in the datastore.
    self._make_events(2, offset=2)

    recurring_data = self.recurring_data.copy()
    params = self.params.copy()
    recurring_data["repetitions"] = Config().USER_MAX_FUTURE_EVENTS
    params["recurring-data"] = json.dumps(recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    self.assertIn("may only have", response.body)

  """ Tests that it properly detects a violation of the 4-week event limit rule
  with recurring events. """
  def test_recurring_four_week_limit(self):
    # Put some initial events in the datastore.
    self._make_events(2, offset=-3)

    recurring_data = self.recurring_data.copy()
    params = self.params.copy()
    recurring_data["repetitions"] = Config().USER_MAX_FOUR_WEEKS
    recurring_data["frequency"] = "daily"
    params["recurring-data"] = json.dumps(recurring_data)
    params["recurring"] = True

    response = self.test_app.post("/new", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    self.assertIn("within a 4-week period", response.body)


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
    date = datetime.date.today() + datetime.timedelta(days=2)
    # Make it last 24 hours or more.
    params["end_date"] = "%d/%d/%d" % (date.month, date.day, date.year)

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

  """ Tests that you can't specify a start time that's later than the end time.
  """
  def test_bad_times(self):
    params = self.params.copy()
    # Make the end time before the start time.
    params["end_time_hour"] = "10"
    params["end_time_ampm"] = "AM"

    response = self.test_app.post("/edit/%d" % (self.event.key().id()), params,
                                  expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("must be after", response.body)

  """ Tests that it forces people to select at least one room. """
  def test_no_room_prohibition(self):
    params = self.params.copy()
    del params["rooms"]

    response = self.test_app.post("/edit/%d" % (self.event.key().id()), params,
                                  expect_errors=True)
    self.assertEqual(400, response.status_int)
    self.assertIn("select a room", response.body)

  """ Tests the fix for one edge case where it double-counts edited events and
  gives an unreasonable error message. """
  def test_no_double_count(self):
    # Make exactly the limit for number of events. (We have one in there to
    # begin with.)
    self._make_events(Config().USER_MAX_FOUR_WEEKS - 1, offset=2)

    # Now, it should let us edit one of them.
    response = self.test_app.post("/edit/%d" % (self.event.key().id()),
                                  self.params)
    self.assertEqual(200, response.status_int)

""" Tests for the ExpireSuspended cron job. """
class ExpireSuspendedCronHandlerTest(BaseTest):
  def setUp(self):
    super(ExpireSuspendedCronHandlerTest, self).setUp()

    # Add an event that should expire.
    start = datetime.datetime.now() + datetime.timedelta(days=1)
    suspended_time = datetime.datetime.now() - \
        datetime.timedelta(days=Config().SUSPENDED_EVENT_EXPIRY)
    user = users.User(email="testy.testerson@hackerdojo.com")
    event = Event(member=user, status="onhold", start_time=start,
                  type="Meetup", estimated_size="10", name="Test Event",
                  details="test", owner_suspended_time=suspended_time,
                  original_status="pending")
    event.put()

    suspended_time += datetime.timedelta(days=5)
    other_event = Event(member=user, status="onhold", start_time=start,
                        type="Meetup", estimated_size="10", name="Test Event",
                        details="test", owner_suspended_time=suspended_time,
                        original_status="pending")
    other_event.put()

    self.event_id = event.key().id()
    self.other_event_id = other_event.key().id()

  """ Tests that running the cron expires events when it should. """
  def test_expires_events(self):
    # Run the cron and make sure it expires.
    response = self.test_app.get("/expire_suspended")
    self.assertEqual(200, response.status_int)

    # One should expire.
    event = Event.get_by_id(self.event_id)
    self.assertEqual("expired", event.status)

    # The other one shouldn't.
    other_event = Event.get_by_id(self.other_event_id)
    self.assertEqual("onhold", other_event.status)


""" The BulkAction and BulkActionCheck handlers are similar enough that it makes
sense to have a common superclass for them. """
class BulkActionBase(BaseTest):
  def setUp(self):
    super(BulkActionBase, self).setUp()

    # Make some events and save their ids.
    events = self._make_events(3)
    self.event_ids = [event.key().id() for event in events]


""" Tests that the bulk action handler works properly. """
class BulkActionHandlerTest(BulkActionBase):
  """ Tests that it works properly when you give it reasonable inputs. """
  def test_post(self):
    events = json.dumps(self.event_ids)
    params = {"action": "onhold", "events": events}

    response = self.test_app.post("/bulk_action", params)
    self.assertEqual(200, response.status_int)

  """ Tests that it handles authorization requirements correctly. """
  def test_authorization_requirements(self):
    events = json.dumps(self.event_ids)
    params = {"action": "approve", "events": events}

    # It should not allow us to approve our own event.
    response = self.test_app.post("/bulk_action", params, expect_errors=True)
    self.assertEqual(400, response.status_int)

    # If we switch users, though, this should be remedied.
    self.testbed.setup_env(user_email="testy.testerson1@gmail.com",
                           user_is_admin="1", overwrite=True)
    response = self.test_app.post("/bulk_action", params)
    self.assertEqual(200, response.status_int)


""" Tests that the bulk action check handler works properly. """
class BulkActionCheckHandlerTest(BulkActionBase):
  """ Tests that it works properly when we give it reasonable inputs. """
  def test_post(self):
    params = {"events": json.dumps(self.event_ids)}

    response = self.test_app.post("/bulk_action_check", params)
    self.assertEqual(200, response.status_int)

    # It should not allow us to approve or not approve because we are not
    # admins, however, we are the owner, so we can do the rest.
    self.assertEqual({"valid": ["onhold", "delete"],
                      "invalid": ["approve", "notapproved"]},
                      json.loads(response.body))

    # If we switch users, though, we should be able to do everything.
    self.testbed.setup_env(user_email="testy.testerson1@gmail.com",
                           user_is_admin="1", overwrite=True)

    response = self.test_app.post("/bulk_action_check", params)
    self.assertEqual(200, response.status_int)

    self.assertEqual({"valid": ["approve", "notapproved", "onhold", "delete"],
                      "invalid": []},
                      json.loads(response.body))
