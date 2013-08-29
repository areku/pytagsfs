# Copyright (c) 2008-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, stat

from pytagsfs.util import ref_self
from pytagsfs.sourcetreemon import SourceTreeMonitor
from pytagsfs.sourcetreemon.deferred import DeferredSourceTreeMonitor
from pytagsfs.debug import log_debug
from pytagsfs.exceptions import (
  MissingDependency,
  InvalidArgument,
  PathNotFound,
  NotADirectory,
  NoSuchWatchError,
  WatchExistsError,
  SourceTreeMonitorError,
)
from pytagsfs.multithreading import token_exchange


################################################################################


ADD = object()
REMOVE = object()
UPDATE = object()

FILE = object()
DIRECTORY = object()


class KqueueEvent(object):
    path = None
    type = None
    is_dir = None
    kevent = None

    def __init__(self, path, type, is_dir, kevent):
        self.path = path
        self.type = type
        self.is_dir = is_dir
        self.kevent = kevent


class KqueueManager(object):
    kqueue = None
    directory_entries = None

    paths = None
    types = None
    base_kevents = None

    def __init__(self, kqueue_mod):
        self.kqueue_mod = kqueue_mod
        self.kqueue = self.kqueue_mod.kqueue()
        self.directory_entries = {}
        self.paths = {}
        self.types = {}
        self.base_kevents = {}

    def watch_directory(self, path):
        try:
            fd = self._get_fd_for_path(path)
        except ValueError:
            pass
        else:
            raise WatchExistsError(path)

        try:
            fd = os.open(path, 0)
        except OSError:
            return

        mode = os.fstat(fd)[stat.ST_MODE]
        if not stat.S_ISDIR(mode):
            raise NotADirectory(path)

        base_kevent = self.kqueue_mod.EV_SET(
          fd,
          self.kqueue_mod.EVFILT_VNODE,
          (
            self.kqueue_mod.EV_ADD |
            self.kqueue_mod.EV_ENABLE |
            self.kqueue_mod.EV_CLEAR
          ),
          self.kqueue_mod.NOTE_WRITE,
        )
        try:
            self.kqueue.kevent(base_kevent, 0, 0)
        except OSError, e:
            if e.errno == errno.ENOENT:
                raise PathNotFound(path)
            else:
                raise SourceTreeMonitorError(str(e))

        try:
            entries = os.listdir(path)
        except OSError:
            os.close(fd)
            return

        self.paths[fd] = path
        self.types[fd] = DIRECTORY
        self.base_kevents[fd] = base_kevent

        self.directory_entries[path] = entries

    def watch_file(self, path):
        try:
            fd = self._get_fd_for_path(path)
        except ValueError:
            pass
        else:
            raise WatchExistsError(path)

        try:
            fd = os.open(path, 0)
        except OSError:
            return

        mode = os.fstat(fd)[stat.ST_MODE]
        if not stat.S_ISREG(mode):
            raise InvalidArgument(path)

        base_kevent = self.kqueue_mod.EV_SET(
          fd,
          self.kqueue_mod.EVFILT_VNODE,
          (
            self.kqueue_mod.EV_ADD |
            self.kqueue_mod.EV_ENABLE |
            self.kqueue_mod.EV_CLEAR
          ),
          (
            self.kqueue_mod.NOTE_WRITE |
            self.kqueue_mod.NOTE_ATTRIB |
            self.kqueue_mod.NOTE_EXTEND |
            self.kqueue_mod.NOTE_DELETE
          ),
        )
        try:
            self.kqueue.kevent(base_kevent, 0, 0)
        except OSError, e:
            if e.errno == errno.ENOENT:
                raise PathNotFound(path)
            else:
                raise SourceTreeMonitorError(str(e))

        self.paths[fd] = path
        self.types[fd] = FILE
        self.base_kevents[fd] = base_kevent

    def watch_path(self, path):
        try:
            self.watch_directory(path)
        except NotADirectory:
            self.watch_file(path)

    def stop_watch(self, path):
        try:
            fd = self._get_fd_for_path(path)
        except ValueError:
            raise NoSuchWatchError(path)

        del self.paths[fd]
        del self.types[fd]
        try:
            del self.directory_entries[path]
        except KeyError:
            pass
        del self.base_kevents[fd]
        os.close(fd)

    def _get_fd_for_path(self, path):
        for fd, path_ in self.paths.items():
            if path_ == path:
                return fd
        raise ValueError(path)

    def get_events(self):
        kevents = self.kqueue.kevent(None, 1024, 0)
        for kevent in kevents:
            try:
                path = self.paths[kevent.ident]
            except KeyError:
                log_debug(
                  'KqueueManager.get_events: unable to find path for fd %u',
                  kevent.ident
                )
                continue

            if self.is_dir(path):
                try:
                    new_entries = os.listdir(path)
                except OSError:
                    # Directory corresponding with path must've been removed.
                    # We'll treat it like an empty directory for now.  We
                    # should eventually get a remove event from the parent
                    # directory.
                    new_entries = []

                old_entries = self.directory_entries[path]
                self.directory_entries[path] = new_entries

                new_entries_set = set(new_entries)
                old_entries_set = set(old_entries)

                added_entries = new_entries_set - old_entries_set
                removed_entries = old_entries_set - new_entries_set

                for entry in added_entries:
                    added_path = os.path.join(path, entry)
                    yield KqueueEvent(
                      os.path.join(path, entry), ADD, None, kevent)
                for entry in removed_entries:
                    yield KqueueEvent(
                      os.path.join(path, entry), REMOVE, None, kevent)
            else:
                if kevent.fflags & self.kqueue_mod.NOTE_DELETE:
                    parent_path = os.path.dirname(path)
                    entry = os.path.basename(path)

                    # Parent directory path *must* be in
                    # self.directory_entries.  No need to catch the KeyError,
                    # because it is a bug if it is not a valid key.
                    known_entry = (entry in self.directory_entries[parent_path])

                    if known_entry:
                        # If the file was deleted but it is still in our local
                        # database of entries, it must be that it was
                        # immediately replaced following removal.  Directory
                        # events are handled such that this situation will not
                        # generate events there, so we have to force the events
                        # here.
                        self.stop_watch(path)
                        self.watch_file(path)

                        # It is unnecessary to provide a remove event in this
                        # case.
                        #yield KqueueEvent(path, REMOVE, False, None)

                        yield KqueueEvent(path, ADD, False, None)
                    else:
                        # File was removed and not replaced.  This will come up
                        # as an event for the parent directory, so we need not
                        # handle it here.
                        pass
                else:
                    # All fflags except NOTE_DELETE indicate a plain old update.
                    yield KqueueEvent(path, UPDATE, False, kevent)

    def is_dir(self, path):
        return (path in self.directory_entries)

    def stop(self):
        for path in self.paths.values():
            self.stop_watch(path)


################################################################################


class KqueueSourceTreeMonitor(SourceTreeMonitor):
    kqueue_manager = None

    def __init__(self):
        try:
            import kqueue
        except ImportError:
            raise MissingDependency('kqueue')

        self.kqueue = kqueue

################################################################################

    # SourceTreeMonitor API

    def start(self, debug = False):
        self.kqueue_manager = KqueueManager(self.kqueue)

    @token_exchange.token_pushed(ref_self)
    def stop(self):
        self.kqueue_manager.stop()

    def supports_threads(self):
        return True

    def supports_writes(self):
        return True

    def can_handle_fork(self):
        return False

    def add_source_dir(self, real_path):
        self.watch_dir(real_path)

    def remove_source_dir(self, real_path):
        self.unwatch_dir(real_path)

    def add_source_file(self, real_path):
        self.watch_file(real_path)

    def remove_source_file(self, real_path):
        self.unwatch_file(real_path)

    def fileno(self):
        return self.kqueue_manager.kqueue.fileno()

    @token_exchange.token_pushed(ref_self)
    def _get_events(self):
        return self.kqueue_manager.get_events()

    def process_events(self):
        for event in self._get_events():
            if event.type is ADD:
                self.add_cb(event.path, event.is_dir)
            elif event.type is REMOVE:
                self.remove_cb(event.path, event.is_dir)
            elif event.type is UPDATE:
                self.update_cb(event.path, event.is_dir)

################################################################################

    @token_exchange.token_pushed(ref_self)
    def _unwatch_path(self, real_path):
        self.kqueue_manager.stop_watch(real_path)

    @token_exchange.token_pushed(ref_self)
    def watch_dir(self, real_path):
        self.kqueue_manager.watch_directory(real_path)

    unwatch_dir = _unwatch_path

    @token_exchange.token_pushed(ref_self)
    def watch_file(self, real_path):
        self.kqueue_manager.watch_file(real_path)

    unwatch_file = _unwatch_path


################################################################################


class DeferredKqueueSourceTreeMonitor(
  DeferredSourceTreeMonitor,
  KqueueSourceTreeMonitor,
):
    pass
