Info
====

This is a modified version of tailon which adds the following features
* Colour logs added
* tailing of network files

Nick Waterton 2nd December 2020

Colour Logs
===========

This functionality is added through the use of grc (grcat) which is heavily modified, and included in this repository. No need to install grc separately.
The colourization of logs is performed using REGEX expressions with the standard grc mechanism, so a `grc.conf` file is expected and an `conf.xxx` file is used.
An example `conf.openhab` grc file is included. see https://github.com/garabik/grc for an explanation of how the configuration works.

**Note:** The mechanism is slightly modified to search the current directory for the `conf.xxx` file in addition to the usual grc directories.

Network Files
=============

Network files can be tailed, if they are added to the `yaml` config file. An example file is included. For remote files, an ip address *must* be used, with username and password.
Files are tailed using `ssh` and `sshpass`, so `sshpass` needs to be installed, and the remote system needs to support the `tail` command.

You need to `ssh` into the remote machine in order to authorize the `ssh` certificates before this will work.

**Note:** SSH is initially quite slow (tailing works at normal speed), so if you have several remote machines configured, receiving the initial file list can take a few seconds. Be patient.

Windows Systems are supported for remote tailing, but it's only tested on Win10, so no idea how robust this is.

Warranty
========

There is no warranty, this project is for my own amusement, and is unsupported. Copied from `tailon-legacy`, I will not be making fixes to this code. Do with it as you please.

Compile front End files
=======================

If you make any changes to the web interface files (colours, javascript or html), you have to recompile the front end files. You need to read https://tailon.readthedocs.io/en/latest/development.html
You will need to install the `requirements-dev.txt` packages. `pip install -r requirements-dev.txt` will do it. You then need to run `npm install`.
```
pip install -r requirements-dev.txt
npm install
```

You can then compile the front end files using:
```
inv webassets --replace
```

Seriously, read https://tailon.readthedocs.io/en/latest/development.html

Notice
======

This project is in maintenance mode. Please consider using the new tailon_,
which is currently under slow, but steady development. The new version comes
with the following improvements:

* Fully self-contained executables. Just download (or build) and run.
* Tiny footprint - the tailon executable sits at 2.5MB in size and uses roughly 10MB of RSS.
* More responsive user-interface.

While some features are missing, it is already usable to a large degree.

----

Tailon
======

Tailon is a self-hosted web application for looking at and searching
through log files. It is little more than a fancy web wrapper around
the following commands::

    tail -f
    tail -f | grep
    tail -f | awk
    tail -f | sed

Documentation:
    http://tailon-legacy.readthedocs.org/en/latest/

Development:
    https://github.com/gvalkov/tailon-legacy

Package:
    http://pypi.python.org/pypi/tailon

Changelog:
    http://tailon-legacy.readthedocs.org/en/latest/changelog.html


.. _tailon: https://github.com/gvalkov/tailon
