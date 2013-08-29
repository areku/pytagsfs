# Copyright (c) 2008-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from pytagsfs.sourcetreemon import SourceTreeMonitor


ADD = 'ADD'
REMOVE = 'REMOVE'
UPDATE = 'UPDATE'


class DeferredSourceTreeMonitor(SourceTreeMonitor):
    event_queue = None

    orig_add_cb = None
    orig_remove_cb = None
    orig_update_cb = None

    def __init__(self):
        super(DeferredSourceTreeMonitor, self).__init__()
        self.event_queue = []

    def set_add_cb(self, add_cb):
        self.orig_add_cb = add_cb
        super(DeferredSourceTreeMonitor, self).set_add_cb(self.dstm_add_cb)

    def set_remove_cb(self, remove_cb):
        self.orig_remove_cb = remove_cb
        super(DeferredSourceTreeMonitor, self).set_remove_cb(
          self.dstm_remove_cb)

    def set_update_cb(self, update_cb):
        self.orig_update_cb = update_cb
        super(DeferredSourceTreeMonitor, self).set_update_cb(
          self.dstm_update_cb)

    def dstm_add_cb(self, path, *args):
        self.event_queue.append((ADD, path) + args)

    def dstm_remove_cb(self, path, *args):
        self.event_queue.append((REMOVE, path) + args)

    def dstm_update_cb(self, path, *args):
        # Look for the last event for this path.  Update events can be collapsed
        # together, since more than one update can be handled no differently
        # than a single update.
        for event in reversed(self.event_queue):
            if event[1] == path:
                if event[0] == UPDATE:
                    # Last event for this path was an update event, no need for
                    # another one (they can be collapsed together).
                    return
                else:
                    # Last event for this path was *not* an update event, so we
                    # need to record this one.
                    break
        self.event_queue.append((UPDATE, path) + args)

    def finish_processing(self):
        while self.event_queue:
            event = self.event_queue.pop(0)
            if event[0] == ADD:
                self.orig_add_cb(*(event[1:]))
            elif event[0] == REMOVE:
                self.orig_remove_cb(*(event[1:]))
            elif event[0] == UPDATE:
                self.orig_update_cb(*(event[1:]))
            else:
                raise ValueError('unknown action %s' % str(event[0]))

    def process_events(self):
        super(DeferredSourceTreeMonitor, self).process_events()
        self.finish_processing()
