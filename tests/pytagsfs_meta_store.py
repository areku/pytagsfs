# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, shutil
from unittest import TestCase

from pytagsfs.fs import PyTagsFileSystem, PyTagsFileSystemOptionParser
from pytagsfs.metastore import UnsettableKeyError
from pytagsfs.metastore.mutagen_ import SimpleMutagenFile

from manager import manager
from common import DATA_DIR, TestWithDir


class PyTagsFileSystemMetaStoreTestCase(TestWithDir):
    test_dir_prefix = 'mts'

    filename = 'silence.ogg'

    test_data_path = None

    def setUp(self):
        super(PyTagsFileSystemMetaStoreTestCase, self).setUp()
        self.test_data_path = os.path.join(self.test_dir, self.filename)
        shutil.copyfile(
          os.path.join(DATA_DIR, self.filename),
          self.test_data_path,
        )

    def tearDown(self):
        os.unlink(self.test_data_path)
        super(PyTagsFileSystemMetaStoreTestCase, self).tearDown()

    def get_meta_store(self):
        return PyTagsFileSystem.get_meta_store(
          PyTagsFileSystemOptionParser.DEFAULT_MOUNT_OPTIONS[
            'metastores']['default']
        )

    def test_parse_tags(self):
        f = SimpleMutagenFile(self.test_data_path)
        f['artist'] = 'foo'
        f['title'] = 'bar'
        f.save()

        p = self.get_meta_store()
        d = p.get(self.test_data_path)
        self.assertEqual(d['artist'], ['foo'])
        self.assertEqual(d['title'], ['bar'])

    def test_apply_tags(self):
        p = self.get_meta_store()
        p.set(self.test_data_path, {'artist': 'foo', 'title': 'bar'})

        f = SimpleMutagenFile(self.test_data_path)
        self.assertEqual(f['artist'], ['foo'])
        self.assertEqual(f['title'], ['bar'])

    def test_apply_does_not_apply_path_name_based_tags(self):
        path_name_based_tags = (
          'extension', 'e', 'filename', 'f', 'parent', 'p')

        p = self.get_meta_store()
        d = p.get(self.test_data_path)

        for t in path_name_based_tags:
            assert t in d

        self.assertRaises(UnsettableKeyError, p.set, self.test_data_path, d)

    def test_apply_does_apply_arbitrary_non_path_name_based_tags(self):
        p = self.get_meta_store()
        p.set(self.test_data_path, {'bizz': 'buzz'})
        f = SimpleMutagenFile(self.test_data_path)
        self.assertEqual(f['bizz'], ['buzz'])

manager.add_test_case_class(PyTagsFileSystemMetaStoreTestCase)
