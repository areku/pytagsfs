# Copyright (c) 2007-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.


class Error(Exception):
    pass


class FuseError(Error):
    errno = None

    def __init__(self, errno):
        self.errno = errno


class ErrorSupportingUnicode(Error):
    def __str__(self):
        return str(unicode(self))


class ErrorWithMessage(ErrorSupportingUnicode):
    def __init__(self, msg):
        self.msg = msg

    def __unicode__(self):
        return unicode(self.msg)


class PathError(Error):
    def __init__(self, path = None):
        self.path = path
        Error.__init__(self, path)

    def __str__(self):
        return str(unicode(self))

    def __unicode__(self):
        if self.path:
            return unicode(self.path)
        return u'[unknown path]'

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, repr(self.path))


class PathNotFound(PathError):
    pass


class FakePathNotFound(PathNotFound):
    pass


class RealPathNotFound(PathNotFound):
    pass


class NotADirectory(PathError):
    pass


class IsADirectory(PathError):
    pass


class PathExists(PathError):
    pass


class DirectoryNotEmpty(PathError):
    pass


class NoMetaDataExists(PathError):
    pass


class NotAnEndPoint(PathError):
    pass


class UnrepresentablePath(ErrorWithMessage):
    pass


class InvalidArgument(Error):
    pass


class ComponentError(ErrorWithMessage):
    pass


class MissingDependency(ComponentError):
    def __init__(self, dependency):
        self.dependency = dependency

    def __unicode__(self):
        return u'missing dependency %s' % unicode(self.dependency)


class NoSuchWatchError(Error):
    pass


class WatchExistsError(Error):
    pass


class SourceTreeMonitorError(ErrorWithMessage):
    pass
