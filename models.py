from google.appengine.ext import db
from google.appengine.api import urlfetch, memcache, users, mail
from datetime import datetime, timedelta, time
from copy import copy
from utils import human_username, local_today, to_sentence_list
import logging
import pytz
import re

from config import Config

ROOM_OPTIONS = (
    # ('Maker Space', 12),
    ('Classroom', 16),
    # ('Conference Room', 10),
    ('Large Event Room', 80),
    ('Loungey', 30),
  )

# GUESTS_PER_STAFF = 25
PENDING_LIFETIME = 30 # days
# Minimum number of hours before event start during which we can RSVP.
RSVP_DEADLINE = 3

class Event(db.Model):
    status  = db.StringProperty(required=True, default='pending', choices=set(
                ['pending', 'understaffed', 'approved', 'not_approved', 'canceled', 'onhold', 'expired', 'deleted']))
    # If the member who created the event is now suspended, what the previous
    # event status was.
    original_status  = db.StringProperty(default=None, choices=set(
                ['pending', 'understaffed', 'approved', 'not_approved', 'canceled', 'onhold', 'expired', 'deleted']))
    member  = db.UserProperty(auto_current_user_add=True)
    name        = db.StringProperty(required=True)
    start_time  = db.DateTimeProperty(required=True)
    end_time    = db.DateTimeProperty()
    staff       = db.ListProperty(users.User)
    rooms       = db.StringListProperty() #choices=set(ROOM_OPTIONS)

    details     = db.TextProperty(required=True)
    admin_notes = db.TextProperty(default="")
    url         = db.StringProperty(default="")
    fee         = db.StringProperty(default="")
    notes       = db.TextProperty(default="")
    type        = db.StringProperty(required=True)
    estimated_size = db.StringProperty(required=True)
    reminded    = db.BooleanProperty(default=False)

    contact_name    = db.StringProperty(default="")
    contact_phone   = db.StringProperty(default="")

    expired = db.DateTimeProperty()
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)

    # Teardown / setup to avoid double-bookings
    setup    = db.IntegerProperty()
    teardown = db.IntegerProperty()

    # An alternate person that will be responsible for the event, that must be
    # specified for events 24 hours or longer.
    other_member = db.StringProperty(default="")

    # When the member who owns this event was suspended, if they are.
    owner_suspended_time = db.DateTimeProperty()

    wifi_password = db.StringProperty(default="")

    @classmethod
    def check_conflict(cls,
                       proposed_start_time, proposed_end_time,
                       setup, teardown,
                       proposed_rooms,
                       optional_existing_event_id = 0):

      # Figure out how long we need to pad the start and end times of the event.
      # This is more complicated that it seems, because setup and teardown can
      # overlap, but there still must be a minimum amount of time between
      # consecutive events.
      conf = Config()
      start_padding = max(int(setup), conf.MIN_EVENT_SPACING)
      end_padding = max(int(teardown), conf.MIN_EVENT_SPACING)

      proposed_start_time -= timedelta(minutes=start_padding)
      proposed_end_time   += timedelta(minutes=end_padding)
      possible_conflicts = cls.all() \
            .filter('end_time >', proposed_start_time) \
            .filter('status IN', ['approved', 'pending', 'onhold'])
      conflicts = []
      for e in possible_conflicts:
        if e.key().id() != optional_existing_event_id:
          if e.start_time < proposed_end_time:
            for r in e.rooms:
              if r in proposed_rooms:
                if e not in conflicts:
                  conflicts.append(e)
      return conflicts


    @classmethod
    def get_all_future_list(cls):
        return cls.all() \
            .filter('start_time >', local_today()) \
            .filter('status IN', ['approved', 'not_approved', 'canceled', 'pending', 'onhold']) \
            .order('start_time')

    @classmethod
    def get_large_list(cls):
        future_list = Event.get_approved_list()
        large_list = []
        for e in future_list:
          if int(e.estimated_size) >= 50:
             large_list.append(e)
        return large_list

    @classmethod
    def get_approved_list(cls):
        return cls.all() \
            .filter('start_time >', local_today()) \
            .filter('status IN', ['approved', 'canceled']) \
            .order('start_time')

    @classmethod
    def get_by_wifi_password(cls, password):
        return cls.all() \
            .filter('wifi_password =', password) \
            .filter('status IN', ['approved']) \
            .order('start_time')

    @classmethod
    def get_approved_list_with_multiday(cls):
        events = list(cls.all() \
            .filter('end_time >', local_today()) \
            .filter('status IN', ['approved', 'canceled']))

        # create dupe event objects for each day of multiday events
        for event in list(events):
            if event.start_time < local_today():
                # remove original if it started before today
                events.remove(event)
            for day in range(1, event.num_days):
                if event.start_time + timedelta(days=day) >= local_today():
                    clone = copy(event)
                    clone.start_time = datetime.combine(event.start_date(), time()) + timedelta(days=day)
                    clone.is_continued = True
                    events.append(clone)


        events.sort(key = lambda event: event.start_time)

        return events

    @classmethod
    def get_recent_past_and_future(cls):
        return cls.all() \
            .filter('start_time >', local_today()  - timedelta(days=1)) \
            .filter('status IN', ['approved', 'canceled']) \
            .order('start_time').fetch(200)

    @classmethod
    def get_recent_past_and_future_approved(cls):
        return cls.all() \
            .filter('start_time >', local_today()  - timedelta(days=1)) \
            .filter('status IN', ['approved']) \
            .order('start_time').fetch(200)

    @classmethod
    def get_pending_list(cls):
        return cls.all() \
            .filter('start_time >', local_today()) \
            .filter('status IN', ['pending', 'understaffed', 'onhold', 'expired']) \
            .order('start_time')

    @classmethod
    # show last 60 days and all future not approved events
    def get_recent_not_approved_list(cls):
        return cls.all() \
            .filter('start_time >', local_today()  - timedelta(days=60)) \
            .filter('status IN', ['not_approved']) \
            .order('start_time')

    def owner(self):
        return human_username(self.member)

    def stafflist(self):
        return to_sentence_list(map(human_username, self.staff))

    def roomlist(self):
        return to_sentence_list(self.rooms)

    def roomlist_as_phrase(self):
        if len(self.rooms) > 0:
            return "in " + self.roomlist()
        else:
            return ""

    def is_staffed(self):
        return len(self.staff) >= self.staff_needed()

    def staff_needed(self):
      return 0
#      if self.estimated_size.isdigit():
#        return int(self.estimated_size) / GUESTS_PER_STAFF
#      else:
#        # invalid data; just return something reasonable
#        return 2

    def is_approved(self):
        """Has the events team approved the event?  Note: This does not
        necessarily imply that the event is in state 'approved'."""
        return self.status in ('understaffed', 'approved', 'cancelled')

    def is_canceled(self):
        return self.status == 'canceled'

    def is_onhold(self):
        return self.status == 'onhold'

    def is_deleted(self):
        return self.status == 'deleted'

    def is_past(self):
        return self.end_time < local_today()

    def is_not_approved(self):
      return self.status == 'not_approved'

    def start_date(self):
        return self.start_time.date()

    def end_date(self):
        return self.end_time.date()

    @property
    def num_days(self):
        num_days = (self.end_date() - self.start_date()).days + 1
        if num_days > 1 and self.end_time.timetuple()[3] < 8:
            # only count that day if the event runs past 8am
            num_days -= 1
        return num_days

    def multiday(self):
        self.num_days > 1

    def approve(self):
        user = users.get_current_user()
        if self.is_staffed():
            self.expired = None
            self.status = 'approved'
            logging.info('%s approved %s' % (user.nickname(), self.name))
        else:
            self.status = 'understaffed'
            logging.info('%s approved %s but it is still understaffed' % (user.nickname, self.name))
        self.put()

    def rsvp(self):
        user = users.get_current_user()
        if user and not self.has_rsvped():
          rsvp = Rsvp(event=self)
          rsvp.put()

    def has_rsvped(self):
        user = users.get_current_user()
        if not user:
          return False
        for existing_rsvp in self.rsvps:
          if existing_rsvp.user == user:
             return True
        return False

    # Works even for logged out users
    def can_rsvp(self):
        if self.has_rsvped():
          return False
        time_till_event = self.start_time.replace(tzinfo=pytz.timezone('US/Pacific')) - datetime.now(pytz.timezone('US/Pacific'))
        hours = time_till_event.seconds/3600+time_till_event.days*24
        return (hours > RSVP_DEADLINE)

    def cancel(self):
        user = users.get_current_user()
        self.status = 'canceled'
        self.put()
        logging.info('%s canceled %s' % (user.nickname(), self.name))

    def on_hold(self):
        user = users.get_current_user()
        self.status = 'onhold'
        self.put()
        logging.info('%s put %s on hold' % (user.nickname(), self.name))

    def not_approved(self):
        user = users.get_current_user()
        self.status = 'not_approved'
        self.put()
        logging.info('%s not_approved %s' % (user.nickname(), self.name))

    def delete(self):
        user = users.get_current_user()
        self.status = 'deleted'
        self.put()
        logging.info('%s deleted %s' % (user.nickname(), self.name))

    def undelete(self):
        user = users.get_current_user()
        self.status = 'pending'
        self.put()
        logging.info('%s undeleted %s' % (user.nickname(), self.name))

    def delete(self):
        user = users.get_current_user()
        self.status = 'deleted'
        self.put()
        logging.info('%s deleted %s' % (user.nickname(), self.name))

    def undelete(self):
        user = users.get_current_user()
        self.status = 'pending'
        self.put()
        logging.info('%s undeleted %s' % (user.nickname(), self.name))

    def expire(self):
        user = users.get_current_user()
        self.expired = datetime.now()
        self.status = 'expired'
        self.put()
        logging.info('%s expired %s' % (user.nickname(), self.name))

    def add_staff(self, user):
        self.staff.append(user)
        if self.is_staffed() and self.status == 'understaffed':
            self.status = 'approved'
        self.put()
        logging.info('%s staffed %s' % (user.nickname(), self.name))

    def remove_staff(self, user):
        self.staff.remove(user)
        if not self.is_staffed() and self.status == 'approved':
            self.status = 'understaffed'
        self.put()
        logging.info('%s staffed %s' % (user.nickname(), self.name))

    def to_dict(self, summarize=False):
        d = dict()
        if summarize:
            props = ['member', 'start_time', 'name', 'type', 'estimated_size', 'end_time', 'rooms', 'status']
        else:
            props = Event.properties().keys()
        for prop in props:
            if prop == 'member':
                d[prop] = getattr(self, prop).email()
            elif prop == 'staff':
                d[prop] = map(lambda x: x.email(), getattr(self, prop))
            elif prop in ['start_time', 'end_time', 'created', 'expired', 'updated']:
                if getattr(self, prop):
                    d[prop] = getattr(self, prop).replace(tzinfo=pytz.timezone('US/Pacific')).strftime('%Y-%m-%dT%H:%M:%S')
            else:
                d[prop] = getattr(self, prop)
        d['id'] = self.key().id()
        return d

    def human_time(self):
        start = self.start_time.strftime("%m/%d/%y %I:%M%p")
        if self.multiday():
            end = self.end_time.strftime("%m/%d/%y %I:%M%p")
        else:
            end = self.end_time.strftime("%I:%M%p")
        out  = "%s to %s" % (start, end)
        if self.multiday():
            out += " (multiday)"
        return out

    def full_url(self):
        protocol = re.compile("^https?:\/\/")
        if protocol.search(self.url):
            return self.url
        return "http://"+self.url

class Feedback(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    event   = db.ReferenceProperty(Event)
    rating  = db.IntegerProperty()
    comment = db.StringProperty(multiline=True)
    created = db.DateTimeProperty(auto_now_add=True)

class Rsvp(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    event   = db.ReferenceProperty(Event, collection_name='rsvps')
    created = db.DateTimeProperty(auto_now_add=True)

class HDLog(db.Model):
    event       = db.ReferenceProperty(Event)
    created     = db.DateTimeProperty(auto_now_add=True)
    user        = db.UserProperty(auto_current_user_add=True)
    description = db.TextProperty()

    @classmethod
    def get_logs_list(cls):
        return cls.all() \
            .order('-created').fetch(500)
