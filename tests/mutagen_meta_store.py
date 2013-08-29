# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from unittest import TestCase

from pytagsfs.metastore.mutagen_ import MutagenFileMetaStore

from manager import manager


class MutagenFileMetaStoreTestCase(TestCase):
    def test_post_process(self):
        store = MutagenFileMetaStore()
        tags = {'n': ['1']}
        store.post_process(tags)
        self.assertEqual(
          tags,
          {'n': ['1'], 'N': ['01'], 'TRACKNUMBER': ['01']},
        )

manager.add_test_case_class(MutagenFileMetaStoreTestCase)
