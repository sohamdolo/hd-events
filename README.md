This is the Hacker Dojo Events application, on the web at [http://events.hackerdojo.com](http://events.hackerdojo.com).

When you clone/checkout this repo, run

    $ fab init

This app uses a special wrapper script to manage externals and unit testing. If
you wish to run tests, run the app on the local dev server, or update the app
on GAE, you need to use the deploy.py script to do this.

Run `./deploy.py -h` for more information.

[Master repo](http://github.com/hackerdojo/hd-events)

[![Build Status](https://travis-ci.org/hackerdojo/hd-events.svg?branch=master)](https://travis-ci.org/hackerdojo/hd-events)

**Note:** Runs only on Google App Engine.
