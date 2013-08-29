# Copyright (c) 2007-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.


SOURCE_TREE_MONITORS = (
  'pytagsfs.sourcetreemon.inotifyx_.DeferredInotifyxSourceTreeMonitor',
  'pytagsfs.sourcetreemon.gamin_.DeferredGaminSourceTreeMonitor',
  'pytagsfs.sourcetreemon.kqueue_.DeferredKqueueSourceTreeMonitor',
  'pytagsfs.sourcetreemon.dummy.DummySourceTreeMonitor',
)


def get_source_tree_monitor(dotted_name):
    from pytagsfs.util import get_obj_by_dotted_name
    source_tree_mon_cls = get_obj_by_dotted_name(dotted_name)
    return source_tree_mon_cls()


class SourceTreeMonitor(object):
    add_cb = lambda *args, **kwargs: None
    remove_cb = lambda *args, **kwargs: None
    update_cb = lambda *args, **kwargs: None

    def set_add_cb(self, add_cb):
        self.add_cb = add_cb

    def set_remove_cb(self, remove_cb):
        self.remove_cb = remove_cb

    def set_update_cb(self, update_cb):
        self.update_cb = update_cb

    def start(self, debug = False):
        '''Start monitoring the source tree.'''

    def stop(self):
        '''Stop monitoring the source tree; clean up.'''

    def fileno(self):
        '''
        Return a file descriptor that can be used to poll for new events.  If
        unsupported, raise NotImplementedError; this is the default behavior,
        so this method can be left unimplemented.
        '''
        raise NotImplementedError()

    def process_events(self):
        '''Process pending events.  Do not block.'''

    def add_source_dir(self, real_path):
        '''
        Monitor source directory ``real_path``, handling errors as follows:

        * If the path is already being watched, raise WatchExistsError.
        * If the path does not exist, raise PathNotFound.
        * If the path exists but is not a directory, raise NotADirectory.
        * If the path cannot be monitored, raise SourceTreeMonitorError.
        '''

    def remove_source_dir(self, real_path):
        '''
        Stop monitoring source directory ``real_path``, handling errors as
        follows:

        * If the path was not being watched, raise NoSuchWatchError.
        '''

    def add_source_file(self, real_path):
        '''
        Monitor source file ``real_path``, handling errors as follows:

        * If the path is already being watched, raise WatchExistsError.
        * If the path does not exist, raise PathNotFound.
        * If the path exists but is not a regular file, raise InvalidArgument.
        * If the path cannot be monitored, raise SourceTreeMonitorError.
        '''

    def remove_source_file(self, real_path):
        '''
        Stop monitor source file ``real_path``, handling errors as follows:

        * If the path was not being watched, raise NoSuchWatchError.
        '''

    def supports_threads(self):
        '''
        Return True if source tree monitor is thread-safe.  The default
        implementation always returns False.
        '''
        return False

    def supports_writes(self):
        '''
        Return True if source tree monitor supports updates due to writing in
        mount tree.  The default implementation always returns False.
        '''
        return False

    def can_handle_fork(self):
        '''
        Return True if the source tree monitor can survive a fork call after the
        start method has been called.  Otherwise, return False to indicate that
        start should not be called until after the filesystem process is forked.
        The default implementation always returns False.
        '''
        return False
