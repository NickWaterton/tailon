# -*- coding: utf-8; -*-

import os
import re
import logging
import argparse
import collections
import glob
import ipaddress
from subprocess import check_output
from . import compat
from tornado.concurrent import run_on_executor
from tornado.ioloop import PeriodicCallback
import concurrent.futures


log = logging.getLogger('utils')


class CompactHelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, *args, **kw):
        super(CompactHelpFormatter, self).__init__(*args, max_help_position=35, **kw)

    def _format_usage(self, *args, **kw):
        usage = super(CompactHelpFormatter, self)._format_usage(*args, **kw)
        return usage.capitalize()

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar = self._metavar_formatter(action, action.dest.upper())(1)
            return metavar
        else:
            res = ', '.join(action.option_strings)
            args_string = self._format_args(action, action.dest.upper())
            res = '%s %s' % (res, args_string)
            return res


class FileUtils:
    def __init__(self, login=None, use_directory_cache=True):
        self.use_directory_cache = use_directory_cache

        self.directory_cache = {}
        self.directory_mtime = {}
        
        self.ip_os = {}
        
        self.sshpass = first_in_path('sshpass')
        self.ssh = first_in_path('ssh')
        if login:
           self.logins = login
        else:
            self.logins = {}
            
    def quote_strings(self, path, sep=os.sep):
        pathlist = [el for el in path.split('/') if el]
        new_path_list = [el if not ' 'in el or '\"' in el else '\"{}\"'.format(el) for el in pathlist]
        return sep.join(new_path_list)
        
    def get_network_command(self, ip, cmd):
        try:
            if isinstance(self.logins, dict):
                login = self.logins.get(ip)
            else:
                login = self.logins
            if login:
                user = login[0]
                password = login[1]
                #cmd = "{} -p {} {} {}@{} {}".format(self.sshpass, self.password, self.ssh, self.user, ip, cmd)
                cmd = [ self.sshpass,
                        '-p',
                        password,
                        self.ssh,
                        '{}@{}'.format(user,ip),
                        cmd]
                log.debug(cmd)
                return check_output(cmd)
        except Exception as e:
            log.error(e)
        return None

    def listdir(self, path):
        if not self.use_directory_cache:
            return listdir_abspath(path)

        mtime = os.stat(path).st_mtime
        if mtime > self.directory_mtime.get(path, 0):
            files = self.listdir_abspath(path)
            self.directory_cache[path] = files
            self.directory_mtime[path] = mtime
        return self.directory_cache[path]
        
    def listnetworkdir(self, ip, path):
        if not self.use_directory_cache:
            return self.get_network_command(ip, 'ls {}'.format(path)).split()
            
        mtime = int(self.get_network_command(ip, 'stat -c %Y {}'.format(path)))
        if mtime > self.directory_mtime.get(path, 0):
            files = self.listdir_netpath(ip, path)
            self.directory_cache[path] = files
            self.directory_mtime[path] = mtime
        return self.directory_cache[path]
           
    def is_network_dir(self, ip, path):
        try:
            ret = self.get_network_command(ip, '[ -d "{}" ] && echo True || echo False'.format(path))
            return ret == 'True\n'
        except Exception as e:
            log.exception(e)
        return False
        
    def is_network_file(self, ip, path):
        try:
            ret = self.get_network_command(ip, '[ -e {} ] && echo True || echo False'.format(path))
            return ret == 'True\n'
        except Exception as e:
            log.exception(e)
        return False
        
    def listdir_netpath(self, ip, path, files_only=True):
        log.info('path is : {}'.format(path))
        self.ip_os.setdefault(ip, None)
        try:
            if not self.ip_os[ip]:
                self.ip_os[ip] = self.get_network_command(ip, 'uname -o').decode('utf-8')   #get remote os type
            if files_only:
                if 'Linux' in self.ip_os[ip]:
                    files =  self.get_network_command(ip, 'find {} -maxdepth 1 -type f'.format(path))
                elif 'Msys' in self.ip_os[ip]:  #windows
                    path = self.quote_strings(path, sep='\\')
                    log.info('windows path is: {}'.format(path))
                    files =  self.get_network_command(ip, 'dir /s/b/a-d {}'.format(path))
            else:
                files = self.get_network_command(ip, 'ls {}'.format(path))
            if files:
                return files.decode('utf-8').splitlines()
        except Exception as e:
            log.exception(e)
        return []    
        
    def statnetfiles(self, ip, files, allow_missing=False):
        for path in files:
            if not allow_missing:
                continue

            if self.is_network_file(ip, path):
                size, mtime = self.get_network_command(ip, 'stat -c "%s %Y" {}'.format(path)).split()
                yield path, int(size), int(mtime)
            elif allow_missing:
                yield path, None, None
            else:
                continue

    @staticmethod
    def listdir_abspath(path, files_only=True):
        paths = [os.path.join(path, i) for i in os.listdir(path)]
        if not files_only:
            return paths
        return [path for path in paths if os.path.isfile(path)]

    @staticmethod
    def statfiles(files, allow_missing=False):
        for path in files:
            if not os.access(path, os.R_OK) and not allow_missing:
                continue

            if os.path.exists(path):
                st = os.stat(path)
                yield path, st.st_size, st.st_mtime
            elif allow_missing:
                yield path, None, None
            else:
                continue


class FileLister:
    def __init__(self, lister, groups, include_missing=False):
        self.lister = lister
        self.groups = groups
        self.include_missing = include_missing
        self.has_changed = False
        
        self.files = collections.OrderedDict()
        self.all_file_names = set()
        self.all_dir_names = set()
        
        self.executor = concurrent.futures.ThreadPoolExecutor(20)

        self.refresh()
        self.periodic = PeriodicCallback(lambda: self.background_refresh(False), 300000) #refresh file list every x seconds (in ms)
        self.periodic.start()

    def is_path_allowed(self, path):
        return path in self.all_file_names
        
    @run_on_executor()
    def background_refresh(self, initial=False):
        '''
        Non blocking version of refresh (runs in a separate thread)
        When initial is False, remote directories are refreshed (which is slow)
        '''
        self.refresh(initial)
        
    def refresh(self, initial=True):
        log.debug('refreshing group file listings')
        self.files = collections.OrderedDict()
        self.all_dir_names = set()

        for group, paths in self.groups.items():
            files = self.files.setdefault(group, [])
            for path in paths:
                log.debug('checking path: {} {}'.format(group, path))
                if is_ipaddress(group):
                    if not initial and path.endswith('/'):
                        self.all_dir_names.add(Path(path))
                        files.extend(self.lister.listdir_netpath(group, path, files_only=True))
                        #log.debug('ip {} added {}'.format(group, files))
                    elif not path.endswith('/'):
                        files.append(path)
                        #log.debug('ip {} added {}'.format(group, path))
                else:
                    if os.path.isdir(path):
                        self.all_dir_names.add(path)
                        files.extend(self.lister.listdir(path))
                    else:
                        files.append(path)
            
            if is_ipaddress(group):
                self.files[group] = [('/{}{}'.format(group,'/{}'.format(file) if not file.startswith('/') else file), None, None) for file in files]
            else:
                self.files[group] = list(self.lister.statfiles(files, self.include_missing))

        afn = (i[0] for values in self.files.values() for i in values)
        afn = {os.path.abspath(i) for i in afn}
        self.has_changed = (afn != self.all_file_names)
        self.all_file_names = afn
        

def is_ipaddress(address):
    try:
        ipaddress.ip_address(address)
        return True
    except:
        pass
    return False
    
    
def first_in_path(*cmds):
    for cmd in cmds:
        path = compat.which(cmd)
        if path:
            return path
    

def parseaddr(arg):
    tmp = arg.split(':')
    port = int(tmp[-1])
    addr = ''.join(tmp[:-1])
    addr = '' if addr == '*' else addr
    return port, addr


def remove_escapes(string):
    #return string
    return re.sub(r'\x1B\[(?:[0-9]{1,2}(?:;[0-9]{1,2})?)?[m|K]', '', string)


def line_buffer(lines, last_line):
    if not lines[-1].endswith('\n'):
        last_line.append(lines[-1])
        return lines[:-1]
    elif last_line:
        lines[0] = ''.join(last_line) + lines[0]
        del last_line[:]  # list.clear() is with py >= 3.3
        return lines
    else:
        return lines
