from google.appengine.api import urlfetch, memcache
from datetime import datetime
import re
import pytz

from shared.api import domain
import json

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
    def __init__(self, user=None, event=None):
        """Constructor.

        Args:
            user: User() object that you want to perform the check on.
            event: Event() object that you want to perform the check against if applicable.
        """
        self.user = user
        self.event = event
        self.is_admin = False
        self.is_owner = False
        self.can_approve = False
        self.can_cancel = False
        self.can_edit = False
        self.can_staff = False
        self.can_unstaff = False

        if self.user:
            self.is_admin = username(self.user) in dojo('/groups/events',force=False)
        if self.event:
            self.is_owner = (self.user == self.event.member)
            self.can_approve = ((self.event.status in ['pending'] or self.event.status in ['onhold'] or self.event.status in ['not_approved'] ) and self.is_admin
                                and not self.is_owner)
            self.can_not_approve = self.event.status not in ['not_approved'] and self.is_admin
            self.can_cancel = self.is_admin or self.is_owner
            self.can_edit = self.is_admin or self.is_owner
            self.can_staff = (self.event.status in ['pending', 'understaffed', 'approved']
                              and self.user not in self.event.staff)
            self.can_unstaff = (self.event.status not in ['canceled', 'deleted']
                                and self.user in self.event.staff)