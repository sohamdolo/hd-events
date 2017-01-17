""" Special REST API for communicating with other applications securely. """

import datetime
import json
import logging

from google.appengine.api import users
from google.appengine.ext import db

import webapp2

from config import Config
from models import Event, HDLog

""" Generic superclass for all API Handlers. """


class ApiHandlerBase(webapp2.RequestHandler):
    # Apps that can use this API.
    _AUTHORIZED_APPS = ("hd-signup-hrd")

    """ A function meant to be used as a decorator. It ensures that an authorized
    app is making the request before running the function.
    function: The function that we are decorating.
    Returns: A wrapped version of the function that interrupts the flow if it
             finds a problem. """

    @classmethod
    def restricted(cls, function):
        """ Wrapper function to return. """

        def wrapper(self, *args, **kwargs):
            app_id = self.request.headers.get("X-Appengine-Inbound-Appid", None)
            logging.debug("Got request from app: %s" % (app_id))

            # If we're not on production, don't deny any requests.
            conf = Config()
            if not conf.is_prod:
                logging.info("Non-production environment, servicing all requests.")

            elif app_id not in self._AUTHORIZED_APPS:
                logging.warning("Not running '%s' for unauthorized app '%s'." % \
                                (function.__name__, app_id))
                self._rest_error("Unauthorized", "Only select apps can do that.", 403)
                return

            return function(self, *args, **kwargs)

        return wrapper

    """ Writes a specific error and aborts the request.
    error_type: The type of error.
    message: The error message.
    status: HTTP status to return. """

    def _rest_error(self, error_type, message, status):
        message = {"type": error_type + "Exception", "message": message}
        message = json.dumps(message)
        logging.error("Rest API error: %s" % (message))

        self.response.clear()
        self.response.out.write(message)
        self.response.set_status(status)

    """ Gets parameters from the request, and raises an error if any are missing.
    *args: Parameters to get.
    Returns: A list of parameter values, in the order specified.
    """

    def _get_parameters(self, *args):
        values = []
        for arg in args:
            value = self.request.get(arg)

            if not value:
                # Try getting the list version of the argument.
                value = self.request.get_all(arg + "[]")

                if not value:
                    message = "Expected argument '%s'." % (arg)
                    self._rest_error("InvalidParameters", message, 400)
                    # So unpacking doesn't fail annoyingly...
                    if len(args) == 1:
                        return None
                    return [None] * len(args)

            values.append(value)

        # If it is a singleton, it is easier not to return it as a list, because
        # then the syntax can just stay the same as if we were unpacking multiple
        # values.
        if len(values) == 1:
            return values[0]
        return values


""" API handler to be called when a user's status changes from suspended to
active or back again. """


class StatusChangeHandler(ApiHandlerBase):
    """ Puts all the pending and approved events for a specified user on hold.
    user: The user in question. """

    def __hold_user_events(self, user):

        events = Event.get_future_events_by_member(member=user)
        # event_query = db.GqlQuery("SELECT * FROM Event WHERE member = :1" \
        #                           " AND status IN :2 AND start_time > :3",
        #                           user, ["pending", "approved"], local_today())

        future_puts = []
        for event in events:
            logging.debug("Suspending event '%s'." % (event.name))

            event.original_status = event.status
            event.status = "suspended"
            event.owner_suspended_time = datetime.datetime.now()
            event_future = db.put_async(event)
            future_puts.append(event_future)

            # Write a log of it.
            log_entry = HDLog(event=event,
                              description="Suspended event \
                                     because owner was suspended.")
            log_entry_future = db.put_async(log_entry)
            future_puts.append(log_entry_future)

        # Wait for all the writes to finish.
        logging.debug("Waiting for all writes to finish...")
        for future_put in future_puts:
            future_put.get_result()

    """ Restores all the user's events that were put on hold because they were
    suspended to their original status. """

    def __restore_user_events(self, user):

        # event_qu    ery = db.GqlQuery("SELECT * FROM Event WHERE member = :1" \
        #                   " AND original_status != NULL", user)

        events = Event.get_future_suspended_events_by_member(member=user)

        future_puts = []
        for event in events.run():
            logging.debug("Restoring event '%s'." % (event.name))

            event.status = event.original_status
            event.original_status = None
            event.owner_suspended_time = None
            event_future = db.put_async(event)
            future_puts.append(event_future)

            # Write a log of it.
            log_entry = HDLog(event=event,
                              description="Restoring event because \
                                    owner is now active.")
            log_entry_future = db.put_async(log_entry)
            future_puts.append(log_entry_future)

        # Wait for all the writes to finish.
        logging.debug("Waiting for all writes to finish...")
        for future_put in future_puts:
            future_put.get_result()

    """ Sets that the user's status has changed.
    Request parameters:
    username: The username of the user.
    status: The user's new status.
    Response: Nothing if successful, otherwise an error message. """

    @ApiHandlerBase.restricted
    def post(self):
        username, status = self._get_parameters("username", "status")
        if not username:
            return

        logging.info("User %s's status changed to %s." % (username, status))

        email = username + "@hackerdojo.com"
        user = users.User(email=email)

        if status == "suspended":
            # Put their events on hold.
            self.__hold_user_events(user)
        elif status == "active":
            # Restore their events to pending status.
            self.__restore_user_events(user)
        else:
            logging.debug("Taking no action for status %s." % (status))

        self.response.out.write(json.dumps({}))


app = webapp2.WSGIApplication([
    ("/api/v1/status_change", StatusChangeHandler)],
    debug=True)
