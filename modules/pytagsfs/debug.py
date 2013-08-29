# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from sclapp import locale

import traceback, logging, time
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps


class VirtualLogFileStream(object):
    def write(self, s):
        # Re-bind write method on first invocation to avoid performance hit
        # from importing on every call (necessary to avoid import loop via
        # pytagsfs.file).
        from pytagsfs.specialfile.logfile import VirtualLogFile
        self.write = VirtualLogFile.log_write
        return self.write(s)

    def flush(self):
        pass


logger = logging.getLogger()


class FormatterWithMicroseconds(logging.Formatter):
    def formatTime(self, record, datefmt):
        ct = self.converter(record.created)
        s = time.strftime(datefmt, ct)
        if '${us}' in s:
            s = s.replace('${us}', '%03d' % record.msecs)
        return s


formatter = FormatterWithMicroseconds(
  '[%(asctime)s] %(message)s',
  '%H:%M:%S,${us}',
)


stderr_handler = logging.StreamHandler()
stderr_handler.setFormatter(formatter)


virtual_log_file_handler = logging.StreamHandler(VirtualLogFileStream())
virtual_log_file_handler.setFormatter(formatter)


logger.addHandler(virtual_log_file_handler)


def set_log_level(lvl):
    logger.setLevel(lvl)


def set_logsize(size):
    from pytagsfs.specialfile.logfile import VirtualLogFile
    VirtualLogFile.set_max_length(size)


stderr_enabled = False

def enable_stderr():
    global stderr_enabled
    if not stderr_enabled:
        logger.addHandler(stderr_handler)
        stderr_enabled = True


def log_debug(*args, **kwargs):
    logger.debug(*args, **kwargs)


def log_info(*args, **kwargs):
    logger.info(*args, **kwargs)


def log_warning(*args, **kwargs):
    logger.warning(*args, **kwargs)


def log_error(*args, **kwargs):
    logger.error(*args, **kwargs)


def log_critical(*args, **kwargs):
    logger.critical(*args, **kwargs)


def log_loud(*args, **kwargs):
    if not stderr_enabled:
        logger.addHandler(stderr_handler)
        try:
            log_critical(*args, **kwargs)
        finally:
            logger.removeHandler(stderr_handler)
    else:
        log_critical(*args, **kwargs)


def log_traceback():
    log_critical(traceback.format_exc())


def ignore_exceptions(*ignored_exceptions):
    def decorator(fn):
        @wraps(fn)
        def new_fn(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ignored_exceptions, e:
                pass
        return new_fn
    return decorator
