from google.appengine.api import mail
from google.appengine.ext import deferred
import random
import os
import unicodedata
import re

from config import Config

FROM_ADDRESS = 'Dojo Events <robot@hackerdojo.com>'
NEW_EVENT_ADDRESS = 'events@hackerdojo.com'
STAFF_ADDRESS = 'staff@hackerdojo.com'

def slugify(str):
    str = unicodedata.normalize('NFKD', str.lower()).encode('ascii','ignore')
    return re.sub(r'\W+','-',str)

""" Convert plain text email bodies to HTML.
body: The body text to convert. """
def to_html(body):
  # Add line breaks.
  body = body.replace("\n", "<br>")
  # Add head and body tags.
  html = "<html><head></head><body>" + body + "</body></html>"
  return html

if Config().is_dev:
    MAIL_OVERRIDE = "nowhere@nowhere.com"
else:
    MAIL_OVERRIDE = False

def bug_owner_pending(e):
  body = """
Event: %s
Owner: %s
Date: %s
URL: https://%s/event/%s-%s
""" % (
    e.name,
    str(e.member),
    e.start_time.strftime('%A, %B %d'),
    os.environ.get('HTTP_HOST'),
    e.key().id(),
    slugify(e.name),)

  if not e.is_approved():
    body += """
Alert! The events team has not approved your event yet.
Please e-mail them at events@hackerdojo.com to see whats up.
"""

  body += """

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com
"""

  html = to_html(body)

  deferred.defer(mail.send_mail, sender=FROM_ADDRESS, to=e.member.email(),
   subject="[Pending Event] Your event is still pending: " + e.name,
   body=body, html=html, _queue="emailthrottle")

def schedule_reminder_email(e):
  body = """

*REMINDER*

Event: %s
Owner: %s
Date: %s
URL: https://%s/event/%s-%s
""" % (
    e.name,
    str(e.owner()),
    e.start_time.strftime('%A, %B %d'),
    os.environ.get('HTTP_HOST'),
    e.key().id(),
    slugify(e.name),)
  body += """

Hello!  Friendly reminder that your event is scheduled to happen at Hacker Dojo.

 * The person named above must be physically present for the duration of the event
 * If the event has been cancelled, resecheduled or moved, you must login and cancel the event on our system

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

"""

  html = to_html(body)

  deferred.defer(mail.send_mail, sender=FROM_ADDRESS, to=e.member.email(),
                 subject="[Event Reminder] " + e.name,
                 body=body, html=html, _queue="emailthrottle")

def notify_owner_confirmation(event):
  body = """This is a confirmation that your event:

%s
on %s

has been submitted to be approved. You will be notified as soon as it's
approved and on the calendar. Here is a link to the event page:

https://events.hackerdojo.com/event/%s-%s

Again, your event is NOT YET APPROVED and not on the calendar.

After the Event:

Cleanup: You must leave Hacker Dojo in the condition you found it in. This
includes cleaning up trash left behind by your attendees as well as hauling
away excess garbage that does not fit in the dumpster. South
Bay Haul Away (408-661-1743) is a company event hosts have enjoyed working with
in the the past.

Room Layout: The room furniture (tables and chairs) must be reset after use in
rooms with standard layouts, including the Large Event Room, the Classroom and
the Conference Room. Details of the layout are posted in each room.))

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

""" % (
    event.name,
    event.start_time.strftime('%A, %B %d'),
    event.key().id(),
    slugify(event.name),)

  html = to_html(body)

  deferred.defer(mail.send_mail ,sender=FROM_ADDRESS, to=event.member.email(),
        subject="[New Event] Submitted but **not yet approved**", body=body,
        html=html)


def notify_event_change(event, modification=False, repeat="Never"):
  """ Send an email to the event owner when it changes.
  Args:
    event: The event that was created/changed.
    modification: Whether it was modified instead of created.
    repeat: A description of when the event repeats. The default it 'never'.
  """
  if (modification):
    subject = "[Event Modified]"
  else:
    subject = "[New Event]"
  subject  += ' %s on %s' % (event.name, event.human_time())
  body="""Event: %s
Member: %s
When: %s
Repeats: %s
Type: %s
Size: %s
Rooms: %s
Contact: %s (%s)
URL: %s
Fee: %s

Details: %s

Notes: %s

https://events.hackerdojo.com/event/%s-%s
""" % (
    event.name,
    event.member.email(),
    event.human_time(),
    repeat,
    event.type,
    event.estimated_size,
    event.roomlist(),
    event.contact_name,
    event.contact_phone,
    event.url,
    event.fee,
    event.details,
    event.notes,
    event.key().id(),
    slugify(event.name),)

  html = to_html(body)

  deferred.defer(mail.send_mail, sender=FROM_ADDRESS, to=possibly_OVERRIDE_to_address(NEW_EVENT_ADDRESS),
      subject=subject, body=body, html=html)

def notify_owner_approved(event):
  body="""Your event is approved and on the calendar!

Friendly Reminder: You must be present at the event and make sure Dojo policies are followed.

Note: If you cancel or reschedule the event, please log in to our system and cancel the event!

Organisers and attendees will be able to connect to HD-Events wifi during the event to get internet access.

Here is the password we generated for you: <b>%s</b>.
Don't forget to give it to your attendees. They will be able to connect 15 min before and until 15 min after your event.

https://events.hackerdojo.com/event/%s-%s

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

""" % (event.wifi_password, event.key().id(), slugify(event.name))

  html = to_html(body)

  deferred.defer(mail.send_mail,sender=FROM_ADDRESS, to=event.member.email(),
      subject="[Event Approved] %s" % event.name, body=body, html=html)

def notify_owner_rsvp(event,user):
  body="""Good news!  %s <%s> has RSVPd to your event.

Friendly Reminder: As per policy, all members are welcome to sit in on any event at Hacker Dojo.

As a courtesy, the Event RSVP system was built such that event hosts won't be surprised by the number of members attending their event.  Members can RSVP up to 48 hours before the event, after that the RSVP list is locked.

https://events.hackerdojo.com/event/%s-%s

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

""" % (user.nickname(),user.email(),event.key().id(), slugify(event.name))

  html = to_html(body)

  deferred.defer(mail.send_mail,sender=FROM_ADDRESS, to=event.member.email(),
      subject="[Event RSVP] %s" % event.name, body=body, html=html)

def notify_deletion(event,user):
  body="""This event has been deleted.

https://events.hackerdojo.com/event/%s-%s

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

""" % (event.key().id(), slugify(event.name))

  html = to_html(body)

  deferred.defer(mail.send_mail,sender=FROM_ADDRESS, to=event.member.email(),
      subject="[Event Deleted] %s" % event.name, body=body, html=html)

def possibly_OVERRIDE_to_address(default):
  if MAIL_OVERRIDE:
    return MAIL_OVERRIDE
  else:
    return default

def notify_owner_expiring(event):
  pass

def notify_owner_expired(event):
  pass

def notify_hvac_change(iat,mode):
  body = """

The inside air temperature was %d.  HVAC is now set to %s.

""" % (iat,mode)

  html = to_html(body)

  deferred.defer(mail.send_mail, sender=FROM_ADDRESS, to=possibly_OVERRIDE_to_address("hvac-operations@hackerdojo.com"),
      subject="[HVAC auto-pilot] " + mode, body=body, html=html, _queue="emailthrottle")


def notify_wifi_password_added(event):
  body="""A password for HD-Events has been generated for your events!

Organisers and attendees will be able to connect to HD-Events wifi during the event to get internet access.

Here is the password we generated for you: <b>%s</b>.
Don't forget to give it to your attendees. They will be able to connect 15 min before and until 15 min after your event.

Friendly Reminder: You must be present at the event and make sure Dojo policies are followed.

Note: If you cancel or reschedule the event, please log in to our system and cancel the event!

https://events.hackerdojo.com/event/%s-%s

Cheers,
Hacker Dojo Events Team
events@hackerdojo.com

""" % (event.wifi_password, event.key().id(), slugify(event.name))

  html = to_html(body)

  deferred.defer(mail.send_mail,sender=FROM_ADDRESS, to=event.member.email(),
      subject="[HD-Events Wifi Password Generated] %s" % event.name, body=body, html=html)
