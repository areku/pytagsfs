# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from pytagsfs.sourcetreemon import SourceTreeMonitor

class DummySourceTreeMonitor(SourceTreeMonitor):
    def start(self, debug = False):
        pass

    def stop(self):
        pass

    def process_events(self):
        pass

    def add_source_dir(self, real_path):
        pass

    def remove_source_dir(self, real_path):
        pass

    def add_source_file(self, real_path):
        pass

    def remove_source_file(self, real_path):
        pass

    def supports_threads(self):
        return True

    def can_handle_fork(self):
        return True
