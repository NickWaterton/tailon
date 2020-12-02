# -*- coding: utf-8; -*-

import logging
import subprocess
from . import compat

from tornado import process


STREAM = process.Subprocess.STREAM
log = logging.getLogger('tailon')


class ToolPaths:
    command_names = {'ctail', 'grep', 'awk', 'sed', 'tail'}

    def __init__(self, overwrites=None):
        self.cmd_grep = self.first_in_path('grep')
        self.cmd_awk  = self.first_in_path('gawk', 'awk')
        self.cmd_sed  = self.first_in_path('gsed', 'sed')
        self.cmd_tail = self.first_in_path('gtail', 'tail')
        self.cmd_sshpass = self.first_in_path('sshpass')
        self.cmd_ssh = self.first_in_path('ssh')

        if overwrites:
            for name, value in overwrites.items():
                setattr(self, name, value)

    def first_in_path(self, *cmds):
        for cmd in cmds:
            path = compat.which(cmd)
            if path:
                return path


#-----------------------------------------------------------------------------
class CommandControl:
    #def __init__(self, toolpaths, follow_names=False):
    def __init__(self, toolpaths, config={}):
        self.toolpaths = toolpaths
        self.follow_names = config['follow-names']
        self.logins = config.get('logins')
           
    def get_user_pass(self, ip):
        if isinstance(self.logins, dict):
            login = self.logins.get(ip)
        else:
            login = self.logins
        user = login[0]
        password = login[1]
        return user, password
        
    def awk(self, script, fn, stdout, stderr, **kw):
        cmd = [self.toolpaths.cmd_awk, '--sandbox', script]
        if fn:
            cmd.append(fn)
        proc = process.Subprocess(cmd, stdout=stdout, stderr=stderr, **kw)
        log.debug('running awk %s, pid: %s', cmd, proc.proc.pid)
        return proc

    def grep(self, regex, fn, stdout, stderr, **kw):
        cmd = [self.toolpaths.cmd_grep, '--text', '--line-buffered', '--color=never', '-i', '-E', regex]
        if fn:
            cmd.append(fn)
        proc = process.Subprocess(cmd, stdout=stdout, stderr=stderr, **kw)
        log.debug('running grep %s, pid: %s', cmd, proc.proc.pid)
        return proc

    def sed(self, script, fn, stdout, stderr, **kw):
        cmd = [self.toolpaths.cmd_sed, '-u', '-e', script]
        if fn:
            cmd.append(fn)
        proc = process.Subprocess(cmd, stdout=stdout, stderr=stderr, **kw)
        log.debug('running sed %s, pid: %s', cmd, proc.proc.pid)
        return proc

    def tail(self, ip, n, fn, stdout, stderr, **kw):
        flag_follow = '-F' if self.follow_names else '-f'
        if ip:
            user, password = self.get_user_pass(ip)
            if '\\' in fn:   #win system
                cmd = [self.toolpaths.cmd_sshpass, '-p', password, self.toolpaths.cmd_ssh, '{}@{}'.format(user, ip), 'tail', '-n', str(n), flag_follow, '\"{}\"'.format(fn[1:])]
            else:
                cmd = [self.toolpaths.cmd_sshpass, '-p', password, self.toolpaths.cmd_ssh, '{}@{}'.format(user, ip), self.toolpaths.cmd_tail, '-n', str(n), flag_follow, fn]
        else:
            cmd = [self.toolpaths.cmd_tail, '-n', str(n), flag_follow, fn]
        proc = process.Subprocess(cmd, stdout=stdout, stderr=stderr, bufsize=1, **kw)
        log.debug('running tail %s, pid: %s', cmd, proc.proc.pid)
        return proc
        
    def ctail(self, ip, n, fn, regex, stdout, stderr, **kw):
        tail = self.tail(ip, n, fn, stdout=subprocess.PIPE, stderr=STREAM, **kw)
        grep = self.grep(regex, None, stdout=STREAM, stderr=STREAM, stdin=tail.stdout)
        tail.stdout.close()
        log.debug('running tail as ctail')
        return tail, grep

    def tail_awk(self, ip, n, fn, script, stdout, stderr):
        tail = self.tail(ip, n, fn, stdout=subprocess.PIPE, stderr=STREAM)
        awk = self.awk(script, None, stdout=STREAM, stderr=STREAM, stdin=tail.stdout)
        return tail, awk

    def tail_grep(self, ip, n, fn, regex, stdout, stderr):
        tail = self.tail(ip, n, fn, stdout=subprocess.PIPE, stderr=STREAM)
        grep = self.grep(regex, None, stdout=STREAM, stderr=STREAM, stdin=tail.stdout)
        tail.stdout.close()
        return tail, grep

    def tail_sed(self, ip, n, fn, script, stdout, stderr):
        tail = self.tail(ip, n, fn, stdout=subprocess.PIPE, stderr=STREAM)
        sed = self.sed(script, None, stdout=STREAM, stderr=STREAM, stdin=tail.stdout)
        tail.stdout.close()
        return tail, sed
