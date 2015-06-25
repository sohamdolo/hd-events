""" Tests for datastore models in the models.py file. """


import datetime
import unittest

from google.appengine.ext import testbed

import models


""" Tests for the Event model. """
class EventTest(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()

    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()

  """ Tests that we can detect conflicts successfully. """
  def test_conflict_detection(self):
    # To begin with, create a new event that we can make things conflict with.
    start_time = datetime.datetime(month=1, day=1, year=2015, hour=10, minute=0)
    end_time = start_time + datetime.timedelta(hours=2)
    event = models.Event(name="Test Event", start_time=start_time,
                         end_time=end_time, type="Meetup",
                         estimated_size="10", setup=15, teardown=15,
                         details="This is a test event.", rooms=["Classroom"])
    event.put()

    # Putting an event a safe distance before should not conflict.
    new_start_time = start_time - datetime.timedelta(hours=1, minutes=30)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    self.assertEqual([], models.Event.check_conflict(new_start_time,
      new_end_time, 15, 15, ["Classroom"]))

    # Putting an event a safe distance after should not conflict.
    new_start_time = end_time + datetime.timedelta(minutes=30)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    self.assertEqual([], models.Event.check_conflict(new_start_time,
        new_end_time, 15, 15, ["Classroom"]))

    # Increasing the setup time should be okay until it starts to get into the
    # time alloted for the actual event before it.
    self.assertEqual([], models.Event.check_conflict(new_start_time,
        new_end_time, 30, 15, ["Classroom"]))

    conflicts = models.Event.check_conflict(new_start_time, new_end_time, 60,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())

    # We also need at least 30 minutes between consecutive events.
    new_start_time = end_time + datetime.timedelta(minutes=15)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    conflicts = models.Event.check_conflict(new_start_time, new_end_time, 15,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())

    # If an event is completely encompassed by another event it should get
    # detected.
    new_start_time = start_time + datetime.timedelta(minutes=30)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    conflicts = models.Event.check_conflict(new_start_time, new_end_time, 15,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())

    # If an event exactly overlaps another event, it should get detected.
    conflicts = models.Event.check_conflict(start_time, end_time, 15,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())

    # If an event overlaps another event not just in setup and teardown on
    # either end, it should get detected.
    new_start_time = start_time - datetime.timedelta(minutes=30)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    conflicts = models.Event.check_conflict(new_start_time, new_end_time, 15,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())

    new_start_time = end_time - datetime.timedelta(minutes=30)
    new_end_time = new_start_time + datetime.timedelta(hours=1)
    conflicts = models.Event.check_conflict(new_start_time, new_end_time, 15,
                                            15, ["Classroom"])
    self.assertEqual(event.key().id(), conflicts[0].key().id())
