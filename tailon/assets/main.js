// global $:false, jQuery:false
// jshint laxcomma: true, sub: true

//----------------------------------------------------------------------------
// globals
var logviewer = null;
var connected = false;
var socket_retries = 10;

//----------------------------------------------------------------------------
// utility functions
function formatBytes(size) {
  var units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  var i = 0;
  while(size >= 1024) {
    size /= 1024;
    ++i;
  }
  return size.toFixed(1) + ' ' + units[i];
}

function formatFilename(state) {
  if (!state.id) return state.text;
  var size = formatBytes($(state.element).data('size'));
  return '<span>' + state.text + '</span>' + '<span style="float:right;">' + size + '</span>';
}

function endsWith(str, suffix) {
  return str.indexOf(suffix, str.length - suffix.length) !== -1;
}

// escapeHtml from mustache.js
var escape_entity_map = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "/": '&#x2F;'
};

function escapeHtml(string) {
  return String(string).replace(/[&<>\/]/g, function (s) {
    return escape_entity_map[s];
  });
}

//----------------------------------------------------------------------------
function isInputFocused() {
  return document.activeElement.nodeName === 'INPUT';
}

function resizeLogview() {
  var toolbar_height = (uimodel.get('pannel-hidden') ? 0 : $('.toolbar').outerHeight(true)); // todo
  logviewer.container.height(window.innerHeight - toolbar_height);
}

//----------------------------------------------------------------------------
// more globals
var wspath = endsWith(window.relativeRoot, '/') ? 'ws' : '/ws';
var wsurl = [window.location.protocol, '//', window.location.host, window.relativeRoot, wspath];
wsurl = wsurl.join('');

//----------------------------------------------------------------------------
// Models.
//----------------------------------------------------------------------------
var CommandModel = Backbone.Model.extend({
  defaults: {
    'mode': 'tail',
    'file':  null,
    'script': null,
    'tail-lines': 60
  }
});

var UiModel = Backbone.Model.extend({
  defaults: {
    'panel-hidden': false
  }
});

//----------------------------------------------------------------------------
// Views.
//----------------------------------------------------------------------------
var ModeSelectView = Backbone.View.extend({
  initialize: function() {
    this.render();
  },

  events: {
    'change': 'modechange'
  },

  modechange: function(event) {
    this.model.set({'mode': event.target.value, 'script': null});
  },

  render: function() {
    this.$el.selectize();
    return this;
  }
});

//----------------------------------------------------------------------------
var FileSelectView = Backbone.View.extend({
  initialize: function() {
    this.render();
  },

  events: {
    'change': 'filechange'
  },

  filechange: function(event) {
    this.model.set({'file': event.target.value});
  },

  render: function() {
    var first_option = this.$el[0].options[0].value;
    this.model.set({'file': first_option});

    this.$el.selectize({
      highlight: false,
      selectOnTab: true
    });
    return this;
  }
});

//----------------------------------------------------------------------------
var ScriptView = Backbone.View.extend({
  initialize: function() {
    this.listenTo(this.model, 'change:mode', this.rendermode);
    this.render();
  },

  events: {
    'change': '_changeScript'
  },

  _changeScript: function() {
    this.model.set({'script': this.$el.val()});
  },

  _placeholders: {
    'awk': '{print $0; fflush()}',
    'sed': 's|.*|&,',
    'grep': '.*'
  },

  rendermode: function() {
    var mode = this.model.get('mode')
      , el = this.$el;

    if (mode in this._placeholders) {
      el.removeAttr('disabled');
      el.val('');
      el.attr('placeholder', this._placeholders[mode]);
    } else {
      el.attr('disabled', 'disabled');
      el.val('');
      el.attr('placeholder', 'mode "'+mode+'" does not accept input');
    }

    return this;
  },

  render: function() {
    return this;
  }
});

//----------------------------------------------------------------------------
var PanelView = Backbone.View.extend({
  initialize: function(options) {
    this.options = options || {};

    this.listenTo(this.model, 'change:panel-hidden', this.hideshowpanel);
    this.listenTo(this.options.cmdmodel, 'change:file', this.updatehrefs); // don't know

    this.$downloadA = this.$el.find('.toolbar-item .button-group .action-download');
  },

  events: {
    'click .toolbar-item .button-group .action-hide-toolbar':  'sethidden',
    'click .toolbar-item .button-group .action-clear-logview': 'clearlogview'
  },

  // Update the download link whenever the selected file changes.
  updatehrefs: function() {
    this.$downloadA.attr('href', 'fetch/' + this.options.cmdmodel.get('file'));
  },

  hideshowpanel: function() {
    if (this.model.get('panel-hidden')) {
      this.$el.slideUp('fast');
    } else {
      this.$el.show();
    }
  },

  sethidden: function() {
    this.model.set({'panel-hidden': true});
  },

  clearlogview: function() {
    logviewer.clear();
  }
});


//----------------------------------------------------------------------------
var ActionsView = Backbone.View.extend({
  initialize: function() {
    this.listenTo(this.model, 'change:panel-hidden', this.hideshowactions);
  },

  events: {
    'click .action-show-toolbar': 'sethidden'
  },

  hideshowactions: function() {
    if (this.model.get('panel-hidden')) {
      this.$el.removeClass('hidden');
    } else {
      this.$el.addClass('hidden');
    }
  },

  sethidden: function() {
    this.model.set({'panel-hidden': false});
  }
});

//----------------------------------------------------------------------------
// Logview "controller".
//----------------------------------------------------------------------------
function logview(selector) {
  var self = this
    , fragment = document.createDocumentFragment()
    , container = $(selector)
    , container_dom = container.get()[0]
    , auto_scroll = true
    , auto_scroll_offset = null
    , history = []
    , lines_of_history = 200  // 0 for infinite history
    , last_span = null
    , last_span_classes = '';

  this.container = container;

  this.logEntry = function(data) {
    var span = document.createElement('span');
    span.innerHTML = data;
    span.className = 'log-entry';
    return span;
  };

  this.logNotice = function(msg) {
    var span = document.createElement('span');
    span.innerHTML = msg;
    span.className = 'log-entry log-notice';
    return span;
  };

  this.write = function(spans) {
    var span, i;

    if (!spans.length) {
      return;
    }

    for (i=0; i<spans.length; i++) {
      span = spans[i];
      history.push(span);
      fragment.appendChild(span);
    }

    container_dom.appendChild(fragment);
    self.scroll();
    self.trimHistory();
    fragment.innerHTML = '';

    if (last_span) {
      last_span.className = last_span_classes;
    }

    last_span = history[history.length-1];
    last_span_classes = last_span.className;
    last_span.className = last_span_classes + ' log-entry-current';
  };

  this.trimHistory = function() {
    if (lines_of_history !== 0 && history.length > lines_of_history) {
      for (var i=0; i<(history.length-lines_of_history); i++) {
        container_dom.removeChild(history.shift());
      }
    }
  };

  this.scroll = function() {
    if (auto_scroll) {
      // autoscroll only if div is scrolled within 40px of the bottom
      auto_scroll_offset = container_dom.scrollTop-(container_dom.scrollHeight-container_dom.offsetHeight);
      if (Math.abs(auto_scroll_offset) < 40) {
        container_dom.scrollTop = container_dom.scrollHeight;
      }
    }
  };

  this.clear = function() {
    container_dom.innerHTML = '';
    fragment.innerHTML = '';
    history = [];
    last_span = null;
  };

  return self;
}


//----------------------------------------------------------------------------
// Communication with backend
//----------------------------------------------------------------------------
var socket = new SockJS(wsurl);

function onOpen() {
  connected = true;
}

function onClose() {
  connected = false;

  if (socket_retries === 0) {
    return;
  }

  window.setTimeout(function () {
    socket_retries -= 1;
    window.socket = new SockJS(wsurl);
    socket.onopen = onOpen;
    socket.onclose = onClose;
    socket.onmessage = onMessage;
  }, 1000);
}

function onMessage(e) {
  var data = JSON.parse(e.data)
    , spans = [], i, line
    , logEntry = logviewer.logEntry
    , logNotice = logviewer.logNotice;

  if ('err' in data) {
    if (data['err'] === 'truncated') {
      var now = window.moment().format();
      spans.push(logNotice(now + ' - ' + data['fn'] + ' - truncated'));
    } else {
      for (i=0; i<data['err'].length; i++) {
        line = data['err'][i];
        spans.push(logNotice(line));
      }
    }
    // var now = window.moment().format();
    // spans.push(logNotice(data['err']));
    // spans.push(logNotice(now + ' - ' + data['fn'] + ' - truncated'));
  } else {
    $.each(data, function (fn, payload) {
      for (i=0; i<payload.length; i++) {
        line = escapeHtml(payload[i]);
        spans.push(logEntry(line.replace(/\n$/, '')));
      }
    });
  }

  logviewer.write(spans);
}

function wscommand(m) {
  var fn = m.get('file')
    , mode = m.get('mode')
    , script = m.get('script')
    , lines = m.get('tail-lines');

  (function() {
    if (connected) {
      if (fn === null) {
        logviewer.clear();
        return;
      }

      var msg = {};
      msg[mode] = fn;
      msg['last'] = lines;

      if (mode != 'tail') {
        if (!script) {
          return;
        } else {
          msg['script'] = script;
        }
      }

      logviewer.clear();
      socket.send(JSON.stringify(msg));
    } else {
      window.setTimeout(arguments.callee, 20);
    }
  })();
}

//----------------------------------------------------------------------------
// Connect everything together.
logviewer = logview('#logviewer');

socket.onopen = onOpen;
socket.onclose = onClose;
socket.onmessage = onMessage;

window.cmdmodel = new CommandModel();
window.uimodel = new UiModel();

cmdmodel.on('change', function(model) {
  wscommand(model);
});

window.fileselectview = new FileSelectView({model: cmdmodel, el: '#logselect  > select'});
window.modeselectview = new ModeSelectView({model: cmdmodel, el: '#modeselect > select'});
window.scriptview = new ScriptView({model: cmdmodel, el: '#scriptinput input'});
window.actionsview = new ActionsView({model: uimodel, el: '.quickbar .button-group'});
window.buttonsview = new PanelView({model: uimodel, cmdmodel: cmdmodel, el: '.toolbar'});

resizeLogview();
$(window).resize(resizeLogview);

// Select first file in list on load.
// window.cmdmodel.model.set({'file': event.target.value});


//----------------------------------------------------------------------------
// shortcuts:
//   ctrl+l - clear screen (major conflict with 'go to addressbar')
//   ctrl+= - increase font size (logview div only)
//   ctrl+- - decrease font size (logview div only)
//   ret    - mark current time
jwerty.key('ctrl+l', logviewer.clear);
jwerty.key('q', function () {
  if (isInputFocused()) { return true; }
  fileselectview.$el.select2('open');
  return false;
});

jwerty.key('w', function () {
  if (isInputFocused()) { return true; }
  modeselectview.$el.select2('open');
  return false;
});

jwerty.key('e', function () {
  if (isInputFocused()) { return true; }
  scriptview.$el.focus();
  return false;
});
