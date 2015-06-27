import logging
import os

from google.appengine.api import app_identity


""" Class for storing specific configuration parameters. """
class Config:
  # Mutually exclusive flags that specify whether the application is running on
  # hd-events-hrd, dev_appserver, or local unit tests.
  is_dev = False
  is_prod = True
  is_testing = False;

  def __init__(self):
    try:
      # Check if we are running on the local dev server.
      software = os.environ["SERVER_SOFTWARE"]
      Config.is_dev = software.startswith("Dev") and "testbed" not in software
    except KeyError:
      pass

    try:
      self.APP_NAME = app_identity.get_application_id()
    except AttributeError:
      # We're calling code outside of GAE, so we must be testing.
      self.APP_NAME = "testbed-test"
    if self.APP_NAME == "testbed-test":
      Config.is_testing = True

    Config.is_prod = not (Config.is_dev or Config.is_testing)

    # The minimum amount of time that must be left between consecutive events,
    # in minutes.
    self.MIN_EVENT_SPACING = 30
    # The maximum amount of future events a single user can have scheduled.
    self.USER_MAX_FUTURE_EVENTS = 10
    # The maximum number of events a single user can have within a four-week
    # period.
    self.USER_MAX_FOUR_WEEKS = 6

    # The hours that we wan to have only one event during. (24-hour time.)
    self.EVENT_HOURS = (9, 17)

    if Config.is_testing:
      logging.debug("Is testing.")
    elif Config.is_dev:
      logging.debug("Is dev server.")
    else:
      logging.debug("Is production server.")
