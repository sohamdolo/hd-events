import cgi
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import urlfetch, memcache, users, mail

import json
import unicodedata
from icalendar import Calendar, Event as CalendarEvent
import logging, urllib, os
from pprint import pprint
from datetime import datetime, timedelta

from models import Event, Feedback, HDLog, ROOM_OPTIONS, PENDING_LIFETIME
from utils import username, human_username, set_cookie, local_today, is_phone_valid, UserRights, dojo
from notices import *

import PyRSS2Gen
import re
import pytz
import keymaster
    
webapp.template.register_template_library('templatefilters.templatefilters')

def slugify(str):
    str = unicodedata.normalize('NFKD', str.lower()).encode('ascii','ignore')
    return re.sub(r'\W+','-',str)

def event_path(event):
    return '/event/%s-%s' % (event.key().id(), slugify(event.name))

class DomainCacheCron(webapp.RequestHandler):
    def get(self):
        noop = dojo('/groups/events',force=True)


class ReminderCron(webapp.RequestHandler):
    def get(self):
        self.response.out.write("REMINDERS")
        today = local_today()
        # remind everyone 3 days in advance they need to show up
        events = Event.all() \
            .filter('status IN', ['approved']) \
            .filter('reminded =', False) \
            .filter('start_time <', today + timedelta(days=3))
        for event in events:
            self.response.out.write(event.name)
            # only mail them if they created the event 2+ days ago
            if event.created < today - timedelta(days=2):
              schedule_reminder_email(event)
            event.reminded = True
            event.put()


class ExpireCron(webapp.RequestHandler):
    def post(self):
        # Expire events marked to expire today
        today = local_today()
        events = Event.all() \
            .filter('status IN', ['pending', 'understaffed']) \
            .filter('expired >=', today) \
            .filter('expired <', today + timedelta(days=1))
        for event in events:
            event.expire()
            notify_owner_expired(event)


class ExpireReminderCron(webapp.RequestHandler):
    def post(self):
        # Find events expiring in 10 days to warn owner
        ten_days = local_today() + timedelta(days=10)
        events = Event.all() \
            .filter('status IN', ['pending', 'understaffed']) \
            .filter('expired >=', ten_days) \
            .filter('expired <', ten_days + timedelta(days=1))
        for event in events:
            notify_owner_expiring(event)

class ExportHandler(webapp.RequestHandler):
    def get(self, format):
        content_type, body = getattr(self, 'export_%s' % format)()
        self.response.headers['content-type'] = content_type
        self.response.out.write(body)

    def export_json(self):
        events = Event.get_recent_past_and_future()
        for k in self.request.GET:
            if self.request.GET[k] and k in ['member']:
                value = users.User(urllib.unquote(self.request.GET[k]))
            else:
                value = urllib.unquote(self.request.GET[k])
            events = events.filter('%s =' % k, value)
        events = map(lambda x: x.to_dict(summarize=True), events)
        return 'application/json', json.dumps(events)

    def export_ics(self):
        events = Event.get_recent_past_and_future()
        url_base = 'http://' + self.request.headers.get('host', 'events.hackerdojo.com')
        cal = Calendar()
        for event in events:
            iev = CalendarEvent()
            iev.add('summary', event.name if event.status == 'approved' else event.name + ' (%s)' % event.status.upper())
            # make verbose description with empty fields where information is missing
            ev_desc = '__Status: %s\n__Member: %s\n__Type: %s\n__Estimated size: %s\n__Info URL: %s\n__Fee: %s\n__Contact: %s, %s\n__Rooms: %s\n\n__Details: %s\n\n__Notes: %s' % (
                event.status,
                event.owner(),
                event.type,
                event.estimated_size,
                event.url,
                event.fee,
                event.contact_name,
                event.contact_phone,
                event.roomlist(),
                event.details,
                event.notes)
            # then delete the empty fields with a regex
            ev_desc = re.sub(re.compile(r'^__.*?:[ ,]*$\n*',re.M),'',ev_desc)
            ev_desc = re.sub(re.compile(r'^__',re.M),'',ev_desc)
            ev_url = url_base + event_path(event)
            iev.add('description', ev_desc + '\n--\n' + ev_url)
            iev.add('url', ev_url)
            if event.start_time:
              iev.add('dtstart', event.start_time.replace(tzinfo=pytz.timezone('US/Pacific')))
            if event.end_time:
              iev.add('dtend', event.end_time.replace(tzinfo=pytz.timezone('US/Pacific')))
            cal.add_component(iev)
        return 'text/calendar', cal.as_string()

    def export_large_ics(self):
        events = Event.get_recent_past_and_future()
        url_base = 'http://' + self.request.headers.get('host', 'events.hackerdojo.com')
        cal = Calendar()
        for event in events:
            iev = CalendarEvent()
            iev.add('summary', event.name + ' (%s)' % event.estimated_size)
            # make verbose description with empty fields where information is missing
            ev_desc = '__Status: %s\n__Member: %s\n__Type: %s\n__Estimated size: %s\n__Info URL: %s\n__Fee: %s\n__Contact: %s, %s\n__Rooms: %s\n\n__Details: %s\n\n__Notes: %s' % (
                event.status,
                event.owner(),
                event.type,
                event.estimated_size,
                event.url,
                event.fee,
                event.contact_name,
                event.contact_phone,
                event.roomlist(),
                event.details,
                event.notes)
            # then delete the empty fields with a regex
            ev_desc = re.sub(re.compile(r'^__.*?:[ ,]*$\n*',re.M),'',ev_desc)
            ev_desc = re.sub(re.compile(r'^__',re.M),'',ev_desc)
            ev_url = url_base + event_path(event)
            iev.add('description', ev_desc + '\n--\n' + ev_url)
            iev.add('url', ev_url)
            if event.start_time:
              iev.add('dtstart', event.start_time.replace(tzinfo=pytz.timezone('US/Pacific')))
            if event.end_time:
              iev.add('dtend', event.end_time.replace(tzinfo=pytz.timezone('US/Pacific')))
            cal.add_component(iev)
        return 'text/calendar', cal.as_string()

    def export_rss(self):
        url_base = 'http://' + self.request.headers.get('host', 'events.hackerdojo.com')
        events = Event.get_recent_past_and_future()
        rss = PyRSS2Gen.RSS2(
            title = "Hacker Dojo Events Feed",
            link = url_base,
            description = "Upcoming events at the Hacker Dojo in Mountain View, CA",
            lastBuildDate = datetime.now(),
            items = [PyRSS2Gen.RSSItem(
                        title = "%s @ %s: %s" % (
                            event.start_time.strftime("%A, %B %d"),
                            event.start_time.strftime("%I:%M%p").lstrip("0"), 
                            event.name),
                        link = url_base + event_path(event),
                        description = event.details,
                        guid = url_base + event_path(event),
                        pubDate = event.updated,
                        ) for event in events]
        )
        return 'application/xml', rss.to_xml()


class EditHandler(webapp.RequestHandler):
    def get(self, id):
        event = Event.get_by_id(int(id))
        user = users.get_current_user()
        show_all_nav = user
        access_rights = UserRights(user, event)
        if access_rights.can_edit:
            logout_url = users.create_logout_url('/')
            rooms = ROOM_OPTIONS
            hours = [1,2,3,4,5,6,7,8,9,10,11,12]
            self.response.out.write(template.render('templates/edit.html', locals()))
        else:
            self.response.out.write("Access denied")

    def post(self, id):
        event = Event.get_by_id(int(id))
        user = users.get_current_user()
        access_rights = UserRights(user, event)
        if access_rights.can_edit:
            try:
                start_time = datetime.strptime('%s %s:%s %s' % (
                    self.request.get('start_date'),
                    self.request.get('start_time_hour'),
                    self.request.get('start_time_minute'),
                    self.request.get('start_time_ampm')), '%m/%d/%Y %I:%M %p')
                end_time = datetime.strptime('%s %s:%s %s' % (
                    self.request.get('end_date'),
                    self.request.get('end_time_hour'),
                    self.request.get('end_time_minute'),
                    self.request.get('end_time_ampm')), '%m/%d/%Y %I:%M %p')
                conflicts = Event.check_conflict(start_time,end_time,self.request.get_all('rooms'), int(id))
                if conflicts:
                    raise ValueError('Room conflict detected')
                if not self.request.get('details'):
                    raise ValueError('You must provide a description of the event')
                if not self.request.get('estimated_size').isdigit():
                    raise ValueError('Estimated number of people must be a number')
                if not int(self.request.get('estimated_size')) > 0:
                    raise ValueError('Estimated number of people must be greater then zero')
                if (  self.request.get( 'contact_phone' ) and not is_phone_valid( self.request.get( 'contact_phone' ) ) ):
                    raise ValueError( 'Phone number does not appear to be valid' )
                if start_time == end_time:
                    raise ValueError('End time for the event cannot be the same as the start time')
                else:
                    notify_event_change(event=event,modification=1)
                    log_desc = ""
                    previous_object = Event.get_by_id(int(id))
                    event.status = 'pending'
                    event.name = self.request.get('name')
                    if (previous_object.name != event.name):
                      log_desc = log_desc + "<strong>Title:</strong> " + previous_object.name + " to " + event.name + "<br />"
                    event.start_time = start_time
                    if (previous_object.start_time != event.start_time):
                      log_desc = log_desc + "<strong>Start time:</strong> " + str(previous_object.start_time) + " to " + str(event.start_time) + "<br />"
                    event.end_time = end_time
                    if (previous_object.end_time != event.end_time):
                      log_desc = log_desc + "<strong>End time:</strong> " + str(previous_object.end_time) + " to " + str(event.end_time) + "<br />"
                    event.estimated_size = cgi.escape(self.request.get('estimated_size'))
                    if (previous_object.estimated_size != event.estimated_size):
                      log_desc = log_desc + "<strong>Est. size:</strong> " + previous_object.estimated_size + " to " + event.estimated_size + "<br />"
                    event.contact_name = cgi.escape(self.request.get('contact_name'))
                    if (previous_object.contact_name != event.contact_name):
                      log_desc = log_desc + "<strong>Contact:</strong> " + previous_object.contact_name + " to " + event.contact_name + "<br />"
                    event.contact_phone = cgi.escape(self.request.get('contact_phone'))
                    if (previous_object.contact_phone != event.contact_phone):
                      log_desc = log_desc + "<strong>Contact phone:</strong> " + previous_object.contact_phone + " to " + event.contact_phone + "<br />"
                    event.details = cgi.escape(self.request.get('details'))
                    if (previous_object.details != event.details):
                      log_desc = log_desc + "<strong>Details:</strong> " + previous_object.details + " to " + event.details + "<br />"
                    event.url = cgi.escape(self.request.get('url'))
                    if (previous_object.url != event.url):
                      log_desc = log_desc + "<strong>Url:</strong> " + previous_object.url + " to " + event.url + "<br />"
                    event.fee = cgi.escape(self.request.get('fee'))
                    if (previous_object.fee != event.fee):
                      log_desc = log_desc + "<strong>Fee:</strong> " + previous_object.fee + " to " + event.fee + "<br />"
                    event.notes = cgi.escape(self.request.get('notes'))
                    if (previous_object.notes != event.notes):
                      log_desc = log_desc + "<strong>Notes:</strong> " + previous_object.notes + " to " + event.notes + "<br />"
                    event.rooms = self.request.get_all('rooms')
                    if (previous_object.rooms != event.rooms):
                      log_desc = log_desc + "<strong>Rooms changed</strong><br />"
                      log_desc = log_desc + "<strong>Old room:</strong> " + previous_object.roomlist() + "<br />"
                      log_desc = log_desc + "<strong>New room:</strong> " + event.roomlist() + "<br />"
                    event.put()
                    log = HDLog(event=event,description="Event edited<br />"+log_desc)
                    log.put()
                    show_all_nav = user
                    access_rights = UserRights(user, event)
                    if access_rights.can_edit:
                        logout_url = users.create_logout_url('/')
                        rooms = ROOM_OPTIONS
                        hours = [1,2,3,4,5,6,7,8,9,10,11,12]
                        if log_desc:
                          edited = "<u>Saved changes:</u><br>"+log_desc
                        self.response.out.write(template.render('templates/edit.html', locals()))
                    else:
                        self.response.out.write("Access denied")

            except ValueError, e:
                error = str(e)
                self.response.out.write(template.render('templates/error.html', locals()))
        else:
            self.response.out.write("Access denied")


class EventHandler(webapp.RequestHandler):
    def get(self, id):

        event = Event.get_by_id(int(id))
        if self.request.path.endswith('json'):
            self.response.headers['content-type'] = 'application/json'
            self.response.out.write(json.dumps(event.to_dict()))
        else:
            user = users.get_current_user()
            if user:
                access_rights = UserRights(user, event)
                logout_url = users.create_logout_url('/')

            else:
                login_url = users.create_login_url('/')
            event.details = db.Text(event.details.replace('\n','<br/>'))
            show_all_nav = user
            event.notes = db.Text(event.notes.replace('\n','<br/>'))
            self.response.out.write(template.render('templates/event.html', locals()))

    def post(self, id):
        event = Event.get_by_id(int(id))
        user = users.get_current_user()
        access_rights = UserRights(user, event)

        state = self.request.get('state')
        if state:
            desc = ''
            if state.lower() == 'approve' and access_rights.can_approve:
                event.approve()
                desc = 'Approved event'
            if state.lower() == 'notapproved' and access_rights.can_not_approve:
                event.not_approved()
                desc = 'Event marked not approved'
            if state.lower() == 'rsvp' and user:
                event.rsvp()
                notify_owner_rsvp(event,user)
            if state.lower() == 'staff' and access_rights.can_staff:
                event.add_staff(user)
                desc = 'Added self as staff'
            if state.lower() == 'unstaff' and access_rights.can_unstaff:
                event.remove_staff(user)
                desc = 'Removed self as staff'
            if state.lower() == 'onhold' and access_rights.can_cancel:
                event.on_hold()
                desc = 'Put event on hold'
            if state.lower() == 'cancel' and access_rights.can_cancel:
                event.cancel()
                desc = 'Cancelled event'
            if state.lower() == 'delete' and access_rights.is_admin:
                event.delete()
                desc = 'Deleted event'
            if state.lower() == 'undelete' and access_rights.is_admin:
                event.undelete()
                desc = 'Undeleted event'
            if state.lower() == 'expire' and access_rights.is_admin:
                event.expire()
                desc = 'Expired event'
            if event.status == 'approved' and state.lower() == 'approve':
                notify_owner_approved(event)
            if desc != '':
                log = HDLog(event=event,description=desc)
                log.put()
        event.details = db.Text(event.details.replace('\n','<br/>'))
        show_all_nav = user
        event.notes = db.Text(event.notes.replace('\n','<br/>'))
        self.response.out.write(template.render('templates/event.html', locals()))

class ApprovedHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        today = local_today()
        show_all_nav = user
        events = Event.get_approved_list_with_multiday()
        tomorrow = today + timedelta(days=1)
        whichbase = 'base.html'
        if self.request.get('base'):
            whichbase = self.request.get('base') + '.html'
        self.response.out.write(template.render('templates/approved.html', locals()))


class MyEventsHandler(webapp.RequestHandler):
    @util.login_required
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        events = Event.all().filter('member = ', user).order('start_time')
        show_all_nav = user
        today = local_today()
        tomorrow = today + timedelta(days=1)
        self.response.out.write(template.render('templates/myevents.html', locals()))


class PastHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        today = local_today()
        show_all_nav = user
        events = Event.all().filter('start_time < ', today).order('-start_time')
        self.response.out.write(template.render('templates/past.html', locals()))


class NotApprovedHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        today = local_today()
        show_all_nav = user
        events = Event.get_recent_not_approved_list()
        self.response.out.write(template.render('templates/not_approved.html', locals()))


class CronBugOwnersHandler(webapp.RequestHandler):
    def get(self):
        events = Event.get_pending_list()
        for e in events:
            bug_owner_pending(e)


class AllFutureHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        show_all_nav = user
        events = Event.get_all_future_list()
        today = local_today()
        tomorrow = today + timedelta(days=1)
        self.response.out.write(template.render('templates/all_future.html', locals()))

class LargeHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        show_all_nav = user
        events = Event.get_large_list()
        today = local_today()
        tomorrow = today + timedelta(days=1)
        self.response.out.write(template.render('templates/large.html', locals()))


class PendingHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        events = Event.get_pending_list()
        show_all_nav = user
        today = local_today()
        tomorrow = today + timedelta(days=1)
        self.response.out.write(template.render('templates/pending.html', locals()))


class NewHandler(webapp.RequestHandler):
    @util.login_required
    def get(self):
        user = users.get_current_user()
        human = human_username(user)
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        rooms = ROOM_OPTIONS
        rules = memcache.get("rules")
        if(rules is None):
          try:
            rules = urlfetch.fetch("http://wiki.hackerdojo.com/api_v2/op/GetPage/page/Event+Policies/_type/html", "GET").content
            memcache.add("rules", rules, 86400)
          except Exception, e:
            rules = "Error fetching rules.  Please report this error to internal-dev@hackerdojo.com."
        self.response.out.write(template.render('templates/new.html', locals()))


    def post(self):
        user = users.get_current_user()
        try:
            start_time = datetime.strptime('%s %s:%s %s' % (
                self.request.get('start_date'),
                self.request.get('start_time_hour'),
                self.request.get('start_time_minute'),
                self.request.get('start_time_ampm')), '%m/%d/%Y %I:%M %p')
            end_time = datetime.strptime('%s %s:%s %s' % (
                self.request.get('end_date'),
                self.request.get('end_time_hour'),
                self.request.get('end_time_minute'),
                self.request.get('end_time_ampm')), '%m/%d/%Y %I:%M %p')
            conflicts = Event.check_conflict(start_time,end_time,self.request.get_all('rooms'))
            if conflicts:
                if "Deck" in self.request.get_all('rooms') or "Savanna" in self.request.get_all('rooms'):
                    raise ValueError('Room conflict detected <small>(Note: Deck &amp; Savanna share the same area, two events cannot take place at the same time in these rooms.)</small>')
                else:
                    raise ValueError('Room conflict detected')
            if not self.request.get('details'):
              raise ValueError('You must provide a description of the event')
            if not self.request.get('estimated_size').isdigit():
              raise ValueError('Estimated number of people must be a number')
            if not int(self.request.get('estimated_size')) > 0:
              raise ValueError('Estimated number of people must be greater then zero')
            if (end_time-start_time).days < 0:
                raise ValueError('End time must be after start time')
            if (  self.request.get( 'contact_phone' ) and not is_phone_valid( self.request.get( 'contact_phone' ) ) ):
                raise ValueError( 'Phone number does not appear to be valid' )
            else:
                event = Event(
                    name = cgi.escape(self.request.get('name')),
                    start_time = start_time,
                    end_time = end_time,
                    type = cgi.escape(self.request.get('type')),
                    estimated_size = cgi.escape(self.request.get('estimated_size')),
                    contact_name = cgi.escape(self.request.get('contact_name')),
                    contact_phone = cgi.escape(self.request.get('contact_phone')),
                    details = cgi.escape(self.request.get('details')),
                    url = cgi.escape(self.request.get('url')),
                    fee = cgi.escape(self.request.get('fee')),
                    notes = cgi.escape(self.request.get('notes')),
                    rooms = self.request.get_all('rooms'),
                    expired = local_today() + timedelta(days=PENDING_LIFETIME), # Set expected expiration date
                    )
                event.put()
                log = HDLog(event=event,description="Created new event")
                log.put()
                notify_owner_confirmation(event)
                notify_event_change(event)
                set_cookie(self.response.headers, 'formvalues', None)

                rules = memcache.get("rules")
                if(rules is None):
                    try:
                        rules = urlfetch.fetch("http://wiki.hackerdojo.com/api_v2/op/GetPage/page/Event+Policies/_type/html", "GET").content
                        memcache.add("rules", rules, 86400)
                    except Exception, e:
                        rules = "Error fetching rules.  Please report this error to internal-dev@hackerdojo.com."
                self.response.out.write(template.render('templates/confirmation.html', locals()))


        except Exception, e:
            message = str(e)
            if 'match format' in message:
                message = 'Date is required.'
            if message.startswith('Property'):
                message = message[9:].replace('_', ' ').capitalize()
            # This is NOT a reliable way to handle erorrs
            #set_cookie(self.response.headers, 'formerror', message)
            #set_cookie(self.response.headers, 'formvalues', dict(self.request.POST))
            #self.redirect('/new')
            error = message
            self.response.out.write(template.render('templates/error.html', locals()))

class SavingHandler(webapp.RequestHandler):
    def get(self, target):
      self.response.out.write(template.render('templates/saving.html', locals()))

class ConfirmationHandler(webapp.RequestHandler):
    def get(self, id):
      event = Event.get_by_id(int(id))
      rules = memcache.get("rules")
      if(rules is None):
          try:
              rules = urlfetch.fetch("http://wiki.hackerdojo.com/api_v2/op/GetPage/page/Event+Policies/_type/html", "GET").content
              memcache.add("rules", rules, 86400)
          except Exception, e:
              rules = "Error fetching rules.  Please report this error to internal-dev@hackerdojo.com."
      user = users.get_current_user()
      logout_url = users.create_logout_url('/')
      self.response.out.write(template.render('templates/confirmation.html', locals()))

class LogsHandler(webapp.RequestHandler):
    @util.login_required
    def get(self):
        user = users.get_current_user()
        logs = HDLog.get_logs_list()
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        show_all_nav = user
        self.response.out.write(template.render('templates/logs.html', locals()))

class FeedbackHandler(webapp.RequestHandler):
    @util.login_required
    def get(self, id):
        user = users.get_current_user()
        event = Event.get_by_id(int(id))
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        self.response.out.write(template.render('templates/feedback.html', locals()))

    def post(self, id):
        user = users.get_current_user()
        event = Event.get_by_id(int(id))
        try:
            if self.request.get('rating'):
                feedback = Feedback(
                    event = event,
                    rating = int(self.request.get('rating')),
                    comment = cgi.escape(self.request.get('comment')))
                feedback.put()
                log = HDLog(event=event,description="Posted feedback")
                log.put()
                self.redirect('/event/%s-%s' % (event.key().id(), slugify(event.name)))
            else:
                raise ValueError('Please select a rating')
        except Exception:
            set_cookie(self.response.headers, 'formvalues', dict(self.request.POST))
            self.redirect('/feedback/new/' + id)

class TempHandler(webapp.RequestHandler):
    def get(self):
        units = {"AC1":"EDD9A758", "AC2":"B65D8121", "AC3":"0BA20EDC", "AC5":"47718E38"} 
        modes = ["Off","Heat","Cool"]
        master = units["AC3"]
        key = keymaster.get('thermkey')
        url = "https://api.bayweb.com/v2/?id="+master+"&key="+key+"&action=data"
        result = urlfetch.fetch(url)
        if result.status_code == 200:
            thdata = json.loads(result.content)
            inside_air_temp = thdata['iat']
            mode = thdata['mode']
            if inside_air_temp <= 66 and modes[mode] == "Cool":
                for thermostat in units:
                    url = "https://api.bayweb.com/v2/?id="+units[thermostat]+"&key="+key+"&action=set&heat_sp=69&mode="+str(modes.index("Heat"))
                    result = urlfetch.fetch(url)
                notify_hvac_change(inside_air_temp,"Heat")
            if inside_air_temp >= 75 and modes[mode] == "Heat":
                for thermostat in units:
                    url = "https://api.bayweb.com/v2/?id="+units[thermostat]+"&key="+key+"&action=set&cool_sp=71&mode="+str(modes.index("Cool"))
                    result = urlfetch.fetch(url)
                notify_hvac_change(inside_air_temp,"Cold")
            self.response.out.write("200 OK")
        else:
            notify_hvac_change(result.status_code,"ERROR connecting to BayWeb API")
            self.response.out.write("500 Internal Server Error")
        

app = webapp.WSGIApplication([
        ('/', ApprovedHandler),
        ('/all_future', AllFutureHandler),
        ('/large', LargeHandler),
        ('/pending', PendingHandler),
        ('/past', PastHandler),
        ('/temperature', TempHandler),
        #('/cronbugowners', CronBugOwnersHandler),
        ('/myevents', MyEventsHandler),
        ('/not_approved', NotApprovedHandler),
        ('/new', NewHandler),
        ('/saving/(.*)', SavingHandler),
        ('/confirm/(\d+).*', ConfirmationHandler),
        ('/edit/(\d+).*', EditHandler),
        # single event views
        ('/event/(\d+).*', EventHandler),
        ('/event/(\d+)\.json', EventHandler),
        # various export methods -- events.{json,rss,ics}
        ('/events\.(.+)', ExportHandler),
        #
        # CRON tasks
        #('/expire', ExpireCron),
        #('/expiring', ExpireReminderCron),
        ('/domaincache', DomainCacheCron),
        #('/reminder', ReminderCron),
        #
        ('/logs', LogsHandler),
        ('/feedback/new/(\d+).*', FeedbackHandler) ],debug=True)

