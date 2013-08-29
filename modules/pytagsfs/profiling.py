# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import time

from pytagsfs.specialfile.logfile import VirtualLogFile
from pytagsfs.debug import log_critical, log_info
from pytagsfs.util import wraps, join_path_abs


_profiling_enabled = False

def enable_profiling():
    log_info('enabling profiling; times are in ms')
    global _profiling_enabled
    _profiling_enabled = True


def disable_profiling():
    log_info('disabling profiling')
    global _profiling_enabled
    _profiling_enabled = False


def profile(fn, *args, **kwargs):
    start = int(1000.0 * time.time())
    try:
        return fn(*args, **kwargs)
    finally:
        duration = int(1000.0 * time.time()) - start
        log_critical(u'PROF %s %s', duration, fn.__name__)


def profiled(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _profiling_enabled:
            return fn(*args, **kwargs)
        return profile(fn, *args, **kwargs)
    return wrapped
