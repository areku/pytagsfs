# Copyright (c) 2008-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os

from pytagsfs.util import ref_self
from pytagsfs.sourcetreemon import SourceTreeMonitor
from pytagsfs.sourcetreemon.deferred import DeferredSourceTreeMonitor
from pytagsfs.debug import log_critical
from pytagsfs.exceptions import (
  MissingDependency,
  NoSuchWatchError,
  WatchExistsError,
  SourceTreeMonitorError,
)
from pytagsfs.multithreading import token_exchange, GLOBAL


################################################################################


class GaminSourceTreeMonitor(SourceTreeMonitor):
    watch_monitor = None

    def __init__(self):
        try:
            import gamin
        except ImportError:
            raise MissingDependency('gamin')

        self.gamin = gamin

        self.event_processors = {
          gamin.GAMChanged: 'process_changed',
          gamin.GAMDeleted: 'process_deleted',
          gamin.GAMStartExecuting: 'process_ignored',
          gamin.GAMStopExecuting: 'process_ignored',
          gamin.GAMCreated: 'process_created',
          gamin.GAMMoved: 'process_deleted',
          gamin.GAMAcknowledge: 'process_ignored',
          gamin.GAMExists: 'process_unexpected',
          gamin.GAMEndExist: 'process_unexpected',
        }

################################################################################

    # SourceTreeMonitor API

    def start(self, debug = False):
        self.watch_monitor = self.gamin.WatchMonitor()
        self.watch_monitor.no_exists()

    @token_exchange.token_pushed(ref_self)
    def stop(self):
        for real_path in self.watch_monitor.objects:
            self.watch_monitor.stop_watch(real_path)

    def supports_threads(self):
        return True

    def supports_writes(self):
        return True

    def can_handle_fork(self):
        return True

    def add_source_dir(self, real_path):
        self.watch_dir(real_path)

    def remove_source_dir(self, real_path):
        self.unwatch_dir(real_path)

    def add_source_file(self, real_path):
        pass

    def remove_source_file(self, real_path):
        pass

    def fileno(self):
        return self.watch_monitor.get_fd()

    @token_exchange.token_pushed(ref_self)
    def process_events(self):
        return self.watch_monitor.handle_events()

################################################################################

    @token_exchange.token_pushed(ref_self)
    def watch_dir(self, real_path):
        if real_path in self.watch_monitor.objects:
            raise WatchExistsError(real_path)

        try:
            self.watch_monitor.watch_directory(
              real_path,
              self.event_callback,
              real_path,
            )
        except self.gamin.GaminException, e:
            # gamin does not provide the reason for the error, so we treat all
            # errors the same way and simply raise SourceTreeMonitorError.
            raise SourceTreeMonitorError(str(e))

    @token_exchange.token_pushed(ref_self)
    def unwatch_dir(self, real_path):
        if real_path not in self.watch_monitor.objects:
            raise NoSuchWatchError(real_path)

        try:
            self.watch_monitor.stop_watch(real_path)
        except self.gamin.GaminException, e:
            # gamin does not provide the reason for the error, so we treat all
            # errors the same way and simply raise SourceTreeMonitorError.
            raise SourceTreeMonitorError(str(e))

    def process_changed(self, real_path):
        if real_path.endswith(os.path.sep):
            # FIXME: Is log_critical necessary here?
            log_critical(
              u'GaminSourceTreeMonitor.process_changed: ignoring %s',
              real_path,
            )
            return
        return self.update_cb(real_path)

    def process_deleted(self, real_path):
        if real_path.endswith(os.path.sep):
            # FIXME: Is log_critical necessary here?
            log_critical(
              u'GaminSourceTreeMonitor.process_deleted: ignoring %s',
              real_path,
            )
            return
        return self.remove_cb(real_path)

    def process_ignored(self, real_path):
        pass

    def process_created(self, real_path):
        if real_path.endswith(os.path.sep):
            # FIXME: Is log_critical necessary here?
            log_critical(
              u'GaminSourceTreeMonitor.process_created: ignoring %s',
              real_path,
            )
            return
        return self.add_cb(real_path)

    def process_unexpected(self, real_path):
        # FIXME: Is log_critical necessary here?
        log_critical(
          u'GaminSourceTreeMonitor.process_unexpected: %s',
          real_path,
        )

    # process_events executes with token identified by self and eventually
    # calls this callback function.  At this point, we no longer need that
    # token, but we must reacquire the global token before calling update_cb,
    # add_cb, or remove_cb.  This is the best place to do that because we are
    # certain of context here.

    @token_exchange.token_pushed(GLOBAL)
    def event_callback(self, entry, kind, watch_path):
        real_path = os.path.join(watch_path, entry)
        return getattr(self, self.event_processors[kind])(real_path)


################################################################################


class DeferredGaminSourceTreeMonitor(
  DeferredSourceTreeMonitor, GaminSourceTreeMonitor):
    pass
