from google.appengine.api import urlfetch, users, memcache
from datetime import datetime, timedelta
import re
import pytz

import random
import string
from shared.api import domain
import json
import logging


LOCAL_TZ = 'America/Los_Angeles'

# TODO: replace use of dojo function with directly using domain from shared lib
dojo = domain


def to_sentence_list(lst):
    lst = map(str, lst)
    count = len(lst)
    if count == 0:
        return ''
    elif count == 1:
        return lst[0]
    else:
        if count > 2:
            pre_and = ', '.join(lst[:-1])
        else:
            pre_and = lst[0]
        return ' and '.join([pre_and, lst[-1]])


def username(user):
    return user.nickname().split('@')[0] if user else None


def human_username(user):
    if user:
        nick = user.nickname().split('@')[0]
        return nick.replace('.', ' ').title()
    else:
        return None


def set_cookie(headers, name, value):
    headers.add_header('Set-Cookie', '%s=%s;' % (name, json.dumps(value)))


def local_today():
    """Return a datetime object representing the start of today, local time."""
    utc_now = pytz.utc.localize(datetime.utcnow())
    local_now = utc_now.astimezone(pytz.timezone(LOCAL_TZ))
    return datetime(*local_now.timetuple()[:3])


def local_now():
    """Return a datetime object representing now in local time."""
    utc_now = pytz.utc.localize(datetime.now())
    now = utc_now.astimezone(pytz.timezone(LOCAL_TZ))
    time_tuple =now.timetuple()
    return datetime(year=time_tuple.tm_year, month=time_tuple.tm_mon, day=time_tuple.tm_mday, hour=time_tuple.tm_hour, minute=time_tuple.tm_min)


def generate_wifi_password():
    """
        Generate a random lower case string with numbers used as wifi password for HD-Events SSID
        Returns: 6 digits lower case string
    """
    num = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return num


def get_phone_parts( in_phone, international_okay=False ):
    """Return the different parts of a phone number: area code, trunk, number, extension, and optionally international code"""
    phone_pattern = '((\d{3})\D*)?(\d{3})\D*(\d{4})(\D+(\d+))?$'
    if international_okay:
        phone_pattern = '(\+?\d{1-3})?\D*' + phone_pattern
    phone_re = re.compile( '^' + phone_pattern )
    try:
        seg = phone_re.search( in_phone ).groups()
    except AttributeError:
        return [ None, None, None, None, None ]
    if international_okay:
        return [ seg[ 2 ], seg[ 3 ], seg[ 4 ], seg[ 6 ], seg[ 0 ] ]
    else:
        return [ seg[ 1 ], seg[ 2 ], seg[ 3 ], seg[ 5 ] ]


def is_phone_valid( in_phone, area_code_required=True, international_okay=True ):
    """Check to make sure a given phone number is valid"""
    parts = get_phone_parts( in_phone, international_okay )
    out = True
    if area_code_required and ( parts[ 0 ] == None or len( parts[ 0 ] ) != 3 ):
        out = False
    if parts[ 1 ] == None or parts[ 2 ] == None or len( parts[ 1 ] ) != 3 or len( parts[ 2 ] ) != 4:
        out = False
    return out

def user_is_admin():
    user = users.get_current_user()
    access_rights = UserRights(user)
    return access_rights.is_admin

class UserRights(object):
    def __init__(self, event=None):
        """Constructor

        Keeps track of the things the current logged-on user can and can't do.

        Args:
            event: Event() object that you want to perform the check against if applicable.
        """
        user = users.get_current_user()

        self.quick_edit = False
        self.user = user
        self.event = event
        self.is_admin = False
        self.is_owner = False
        self.can_approve = False
        self.can_cancel = False
        self.can_delete = False
        self.can_undelete = False
        self.can_edit = False
        self.can_staff = False
        self.can_unstaff = False

        self.is_admin = users.is_current_user_admin()

        if self.event:
            """ Allow people 30 minutes to do quick edits, like deletion. """
            if (datetime.now() - event.created) <= timedelta(minutes=30):
                self.quick_edit = True
            self.is_owner = (self.user == self.event.member)
            self.can_approve = ((self.event.status in ['pending'] or self.event.status in ['onhold'] or self.event.status in ['not_approved'] ) and self.is_admin)
            self.can_not_approve = self.event.status not in ['not_approved'] and self.is_admin
            self.can_cancel = self.is_admin or self.is_owner
            self.can_delete = self.is_admin or ( self.is_owner and self.quick_edit )
            self.can_undelete = self.is_admin or self.is_owner
            self.can_edit = self.is_admin or self.is_owner
            self.can_staff = (self.event.status in ['pending', 'understaffed', 'approved']
                              and self.user not in self.event.staff)
            self.can_unstaff = (self.event.status not in ['canceled', 'deleted']
                                and self.user in self.event.staff)
