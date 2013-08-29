# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps

from pytagsfs.sourcetreerep import SourceTreeRepresentation

def process_events_before_calling(wrapped):
    @wraps(wrapped)
    def wrapper(self, *args, **kwargs):
        self.monitor.process_events()
        return wrapped(self, *args, **kwargs)
    return wrapper

def process_events_after_calling(wrapped):
    @wraps(wrapped)
    def wrapper(self, *args, **kwargs):
        retval = wrapped(self, *args, **kwargs)
        self.monitor.process_events()
        return retval
    return wrapper

class PollInLineSourceTreeRepresentation(SourceTreeRepresentation):
    populate = process_events_after_calling(SourceTreeRepresentation.populate)
    getattr = process_events_before_calling(SourceTreeRepresentation.getattr)
