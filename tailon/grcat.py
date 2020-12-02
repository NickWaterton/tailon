#! /usr/bin/env python3

#stolen from grcat

from __future__ import print_function

import sys, os, string, re, signal, errno, logging
from pathlib import Path

log = logging.getLogger('tailon')

# ignore ctrl C - this is not ideal for standalone grcat, but
# enables propagating SIGINT to the other subprocess in grc
#signal.signal(signal.SIGINT, signal.SIG_IGN)

class colourize:
    '''
    colour lines using ANSI codes
    '''
    
    #some default definitions see https://notes.burke.libbey.me/ansi-escape-codes/
    colours = {
                'none'       :    "",
                'default'    :    "\033[0m",
                'bold'       :    "\033[1m",
                'underline'  :    "\033[4m",
                'blink'      :    "\033[5m",
                'reverse'    :    "\033[7m",
                'concealed'  :    "\033[8m",

                'black'      :    "\033[30m", 
                'red'        :    "\033[31m",
                'green'      :    "\033[32m",
                'yellow'     :    "\033[33m",
                'blue'       :    "\033[34m",
                'magenta'    :    "\033[35m",
                'cyan'       :    "\033[36m",
                'white'      :    "\033[37m",
                
                #background colours
                'on_black'   :    "\033[40m", 
                'on_red'     :    "\033[41m",
                'on_green'   :    "\033[42m",
                'on_yellow'  :    "\033[43m",
                'on_blue'    :    "\033[44m",
                'on_magenta' :    "\033[45m",
                'on_cyan'    :    "\033[46m",
                'on_white'   :    "\033[47m",

                'beep'       :    "\007",
                'previous'   :    "prev",
                'unchanged'  :    "unchanged",

                # non-standard attributes, supported by some terminals
                'dark'         :    "\033[2m",
                'italic'       :    "\033[3m",
                'rapidblink'   :    "\033[6m",
                'strikethrough':    "\033[9m",

                # aixterm bright color codes
                # prefixed with standard ANSI codes for graceful failure
                'bright_black'      :    "\033[30;90m",
                'bright_red'        :    "\033[31;91m",
                'bright_green'      :    "\033[32;92m",
                'bright_yellow'     :    "\033[33;93m",
                'bright_blue'       :    "\033[34;94m",
                'bright_magenta'    :    "\033[35;95m",
                'bright_cyan'       :    "\033[36;96m",
                'bright_white'      :    "\033[37;97m",

                'on_bright_black'   :    "\033[40;100m", 
                'on_bright_red'     :    "\033[41;101m",
                'on_bright_green'   :    "\033[42;102m",
                'on_bright_yellow'  :    "\033[43;103m",
                'on_bright_blue'    :    "\033[44;104m",
                'on_bright_magenta' :    "\033[45;105m",
                'on_bright_cyan'    :    "\033[46;106m",
                'on_bright_white'   :    "\033[47;107m",
                }
    
    colour_words = ['colours', 'colors', 'colour', 'color']
    keywords = ["regexp", "count", "command", "skip", "replace", "concat"] + colour_words

    def __init__(self, conffile=None, cfile=None, match_name=''):
        log.debug('colourize loaded')
        self.conffile = conffile
        self.cfile = cfile
        self.match_name = match_name
        self.confdir = None
        self.ll = {}
        self.prevcolour = self.colours['default']
        self.prevcount = 'more'
        self.blockcolour = None
        self.regexplist = []
        self.set_cfile()
        
    def set_cfile(self, conffile=None, cfile=None, match_name=''):
        if cfile:
            self.cfile = None
        else:
            if conffile:
                self.conffile = conffile
            else:
                self.conffile = self.get_conffile()
                
            if match_name:
                self.match_name = match_name
                
            if self.conffile and self.match_name:
                log.debug('looking for matching colour configuration file for: {}'.format(self.match_name))
                cfile = self.load_conffile(self.match_name)
                log.debug('match found: {}'.format(cfile))
                
        if not self.confdir:
            self.confdir = self.get_conffile_path()
        if self.cfile != cfile:
            self.cfile = cfile
            log.debug('loading colour config file: {}'.format(self.cfile))
            self.load_cfile()   #load specific config file
        else:
            log.debug('{} already loaded'.format(cfile))
        
    def get_conffile(self):
        conffilenames=['/usr/local/etc/grc.conf', '/etc/grc.conf', './grc.conf']
        for name in conffilenames:
            if os.path.exists(name) and not os.path.isdir(name):
                return name
        return None
        
    def load_conffile(self, match_name):
        '''
        search file grc.conf for regex matching command of filename
        return the name of the conf file for that match
        '''
        found = False
        with open(self.conffile, 'r') as f:
            for line in f:
                if found:
                    return line.strip() #return next line after regex match
                if not line or line[0] in '#\r\n':
                    continue
                regexp = line.strip()
                if re.search(regexp, match_name):
                    found=True
                    continue
        return None
        
    def get_conffile_path(self):
        conffilepath = ['~/.grc/', '/usr/local/share/grc/', '/usr/share/grc/' ]
        for conf_dir in conffilepath:
            if os.path.exists(conf_dir) and os.path.isdir(conf_dir):
                return conf_dir
        return None
              
    def load_cfile(self):
        '''
        loads grc conf file format into self.regexplist
        '''
        #find self.cfile
        for pathname in ['./', self.confdir]:
            log.debug('searching for {} in {}'.format(self.cfile, pathname))
            for file_path in Path(pathname).rglob(self.cfile):
                file = file_path
                break
            else:
                file = None
            if file:
                log.debug('file found : {}'.format(file))
                break
        else:
            return None
        
        #load it
        self.regexplist = []
        with open(file, 'r') as f:
            for line in f:
                try:
                    if any([line.startswith(keyword) for keyword in self.keywords]):    #if we find keyword
                        fields = line.rstrip('\r\n').split('=', 1)
                        if len(fields) != 2:
                            raise ValueError('Error in configuration, I expect keyword=value line But I got instead: {}'.format(line))
                        keyword, value = fields[0].lower(), fields[1]
                        if keyword in self.ll.keys():
                            self.save_regex()
                        log.debug('got keyword: {}, value: {}'.format(keyword, value))
                        self.add_regex_colour(keyword, value)
                except Exception as e:
                    log.exception(e)
            self.save_regex()      
        log.debug('loaded {} regex'.format(len(self.regexplist)))
        
    def add2list(self, m, patterncolour):
        '''
        this creates a list of positions and colour codes from regex matches
        m is the regex matches object
        patterncolour is a list of the ansi codes for the colours
        '''
        clist = []
        for group in range(0, len(m.groups()) +1):
            if group < len(patterncolour):
                clist.append((m.start(group), m.end(group), patterncolour[group]))
            else:
                clist.append((m.start(group), m.end(group), patterncolour[-1])) # was patterncolour[0] (ie use first colour for all subsequent), changed to last colour...
        return clist

    def get_colour(self, x):
        try:
            if x in self.colours:
                return self.colours[x]
            elif len(x)>=2 and x[0]=='"' and x[-1]=='"':
                return eval(x)
            else:
                raise ValueError('Bad colour specified: {}'.format(x))
        except Exception as e:
            log.error(e)
        return self.colours['default']

    def add_regex_colour(self, keyword, value):
        self.ll[keyword] = value
        if keyword in self.colour_words:
            self.ll['colours'] = [''.join([self.get_colour(x) for x in colgroup.split()]) for colgroup in value.split(',')]
        if keyword == 'regexp':
            try:
                self.ll['regexp'] = re.compile(value).finditer
            except Exception as e:
                if hasattr(e, 'pos'):
                    log.error('in file: {} REGEX error: {}'.format(self.cfile, e))
                    log.error(value)
                    log.error('{}^'.format(' '*int(e.pos)))
                else:
                    log.error('in file: {} REGEX error: {} in line {}'.format(self.cfile, e, value))
        
    def save_regex(self):
        if self.ll:
            log.debug('saving: {}'.format(self.ll))
            self.regexplist.append(self.ll)
            self.ll = {}
            
    def print_lines(self, lines):
        print(self.colour_lines(lines), end='')
            
    def colour_lines(self, lines):
        #colourize list of lines, or lines string
        if isinstance(lines, (list, tuple)): 
            new_lines = []
            for line in lines:
                new_lines.append(self.colour_line(line))
            return new_lines
        return self.colour_line(lines)
                    
    def colour_line(self, lines):
        if not self.cfile:
            self.set_cfile()
        if not self.regexplist:
            return lines
        currcount = None
        output_lines = []
        for line in lines.splitlines(True):
            clist = []
            skip = False
            match = False
            for pattern in self.regexplist:
                if currcount == 'stop' or skip:
                    break
                currcount = pattern.get('count','more').lower()
                for m in pattern['regexp'](line):
                    match = True
                    if currcount == "previous":
                        currcount = self.prevcount
                    if 'replace' in pattern:
                        line = re.sub(m.re, pattern['replace'], line)
                    if 'colours' in pattern:
                        if currcount == "block":
                            self.blockcolour = pattern['colours'][0]
                            break
                        elif currcount == "unblock":
                            self.blockcolour = None
                        clist.extend(self.add2list(m, pattern['colours']))
                    if 'concat' in pattern:
                        with open(pattern['concat'], 'a') as f :
                            f.write(line)
                        if 'colours' not in pattern:
                            break
                    if 'command' in pattern:
                        os.system(pattern['command'])
                        if 'colours' not in pattern:
                            break
                    if 'skip' in pattern:
                        skip = pattern['skip'].lower() in ("yes", "1", "true")
                        break                  
                    if currcount in ('stop', 'once'):
                        break
                if not match:
                    currcount = None
                else:
                    self.prevcount = currcount
                if currcount == 'stop' or skip:
                    break
                    
            if not skip:
                output_lines.append(self.process_line(line, clist))
                
        return ''.join(output_lines)
        
        
    def process_line(self, line, clist):
        if self.blockcolour:
            self.prevcolour = self.blockcolour
            #include default as a prefix as a fallback colour if the terminal doesn't support the selected colour
            return self.colours['default']+self.blockcolour + line + self.colours['default']  #leave default at the end of each line
        
        cline = self.make_linemap(clist, len(line))   
        nline = []
        clineprev = ''
        for i in range(len(line)):
            if cline[i] == clineprev: 
                nline.append(line[i])
            else:
                nline.append(cline[i] + line[i])
                clineprev = cline[i]
        return ''.join(nline)
                
    def make_linemap(self, clist, len_line):
        '''
        makes a map of the line colours, one colour code per character (initially default), then replaces each code with the colours
        mapped in clist.
        returns the line colour map
        '''
        cline = (len_line+1)*[self.colours['default']]  #initial map, leave default at the end of each line
        for i in clist:
            #each position in the string has its own colour, this is a tuple of the form (start, end, colour)
            #cline is a map of the colours in the line, as groups start and stop can overlap
            #include default as a prefix as a fallback colour if the terminal doesn't support the selected colour
            if i[2] in ('prev', 'previous'):
                cline[i[0]:i[1]] = [self.colours['default']+self.prevcolour]*(i[1]-i[0])
            elif i[2] != 'unchanged':
                cline[i[0]:i[1]] = [self.colours['default']+i[2]]*(i[1]-i[0])
                self.prevcolour = i[2]
        return cline
            
def main():
    import subprocess
    logging.basicConfig(level=logging.DEBUG)
    log.info('starting')
    if len(sys.argv) < 2:
        log_file = '/var/log/openhab2/openhab.log'
    else:
        log_file = sys.argv[1]
    cline = colourize(match_name=log_file)
    cmd = ['/usr/bin/tail', '-n', '10', '-F', log_file]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
        while True:
            cline.print_lines(proc.stdout.readline().decode('utf-8'))
    
    log.info('done')

if __name__ == "__main__":
    main()