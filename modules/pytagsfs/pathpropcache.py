# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

class PathPropCache(object):
    d = None

    def __init__(self):
        self.d = {}

    def put(self, path, key, value):
        try:
            path_d = self.d[path]
        except KeyError:
            path_d = {}
            self.d[path] = path_d
        path_d[key] = value

    def get(self, path, key):
        return self.d[path][key]

    def prune(self, path = None, key = None):
        if key is not None:
            if path is None:
                raise ValueError('Must specify path if key is specified.')
            del self.d[path][key]
            return
        if path is not None:
            del self.d[path]
            return
        self.d.clear()
