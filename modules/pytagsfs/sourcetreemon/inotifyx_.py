# Copyright (c) 2007-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, errno

from pytagsfs.util import ref_self
from pytagsfs.sourcetreemon import SourceTreeMonitor
from pytagsfs.sourcetreemon.deferred import DeferredSourceTreeMonitor
from pytagsfs.exceptions import (
  MissingDependency,
  PathNotFound,
  NotADirectory,
  NoSuchWatchError,
  WatchExistsError,
  SourceTreeMonitorError,
)
from pytagsfs.debug import log_warning, log_error, log_critical
from pytagsfs.multithreading import token_exchange


class InotifyxSourceTreeMonitor(SourceTreeMonitor):
    wd_to_path = None
    path_to_wd = None
    fd = None

    def __init__(self):
        try:
            import inotifyx
        except ImportError:
            raise MissingDependency('inotifyx')

        self.inotifyx = inotifyx
        self.event_mask = (
          inotifyx.IN_DELETE |
          inotifyx.IN_CREATE |
          inotifyx.IN_MOVED_FROM |
          inotifyx.IN_MOVED_TO |
          inotifyx.IN_MODIFY |
          inotifyx.IN_ATTRIB
        )

        self.wd_to_path = {}
        self.path_to_wd = {}

    def start(self, debug = False):
        self.fd = self.inotifyx.init()

    @token_exchange.token_pushed(ref_self)
    def watch_dir(self, real_path):
        if real_path in self.path_to_wd:
            raise WatchExistsError(real_path)

        try:
            wd = self.inotifyx.add_watch(self.fd, real_path, self.event_mask)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise PathNotFound(real_path)
            elif e.errno == errno.ENOTDIR:
                raise NotADirectory(real_path)
            else:
                if e.errno == errno.ENOSPC:
                    msg = '%s (try increasing inotify max_user_watches)' % e
                else:
                    msg = str(e)
                raise SourceTreeMonitorError(msg)

        self.path_to_wd[real_path] = wd
        self.wd_to_path[wd] = real_path

    @token_exchange.token_pushed(ref_self)
    def unwatch_dir(self, real_path):
        try:
            wd = self.path_to_wd[real_path]
        except KeyError:
            raise NoSuchWatchError(real_path)

        try:
            self.inotifyx.rm_watch(self.fd, wd)
        except IOError, e:
            # EINVAL indicates the diretory disappeared.
            if e.errno != errno.EINVAL:
                raise SourceTreeMonitorError(str(e))

        del self.path_to_wd[real_path]
        del self.wd_to_path[wd]

    ### SourceTreeMonitor API:

    @token_exchange.token_pushed(ref_self)
    def stop(self):
        os.close(self.fd)

    def add_source_dir(self, real_path):
        self.watch_dir(real_path)

    def remove_source_dir(self, real_path):
        self.unwatch_dir(real_path)

    def add_source_file(self, real_path):
        pass

    def remove_source_file(self, real_path):
        pass

    def supports_threads(self):
        return True

    def supports_writes(self):
        return True

    def can_handle_fork(self):
        return True

    def fileno(self):
        return self.fd

    def _process_event(self, event):
        try:
            basepath = self.wd_to_path[event.wd]
        except KeyError:
            # We got an event for a path that we are no longer watching.  If
            # the event is IN_IGNORED, this is expected since we get IN_IGNORED
            # when we remove the watch, which happens after the directory is
            # removed.  Otherwise, the event is late, which won't usually
            # happen for other event types, but could if paths were rapidly
            # added and removed.
            if not (event.mask & self.inotifyx.IN_IGNORED):
                log_warning(
                  'InotifyxSourceTreeMonitor: late event: %s, %r',
                  event,
                  event,
                )
            return

        if event.name:
            path = os.path.join(basepath, event.name)
        else:
            path = basepath

        is_dir = bool(event.mask & self.inotifyx.IN_ISDIR)

        if event.mask & self.inotifyx.IN_DELETE:
            self.remove_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_CREATE:
            self.add_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_MOVED_FROM:
            self.remove_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_MOVED_TO:
            self.add_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_MODIFY:
            self.update_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_ATTRIB:
            self.update_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_UNMOUNT:
            self.remove_cb(path, is_dir)
        elif event.mask & self.inotifyx.IN_IGNORED:
            pass
        elif event.mask & self.inotifyx.IN_Q_OVERFLOW:
            log_critical(
              'InotifyxSourceTreeMonitor: '
              'event queue overflowed, events were probably lost'
            )
        else:
            raise ValueError(
              'failed to match event mask: %s' % event.get_mask_description()
            )

    @token_exchange.token_pushed(ref_self)
    def _get_events(self):
        return self.inotifyx.get_events(self.fd, 0)

    def process_events(self):
        for event in self._get_events():
            self._process_event(event)


class DeferredInotifyxSourceTreeMonitor(
  DeferredSourceTreeMonitor, InotifyxSourceTreeMonitor):
    pass
