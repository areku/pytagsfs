# coding: utf-8

# Copyright (c) 2005-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

# A lot of this code was ripped out of sclapp's test/common.py

import doctest, os, platform, errno, glob, time

from unittest import (
  TestSuite,
  defaultTestLoader,
  TextTestRunner,
  TestCase as _TestCase,
)

# These are used to determine which SourceTreeMonitor implementations should be
# tested on the current platform:
NO_INOTIFY_PLATFORMS = ('Darwin', 'FreeBSD', 'NetBSD', 'OpenBSD')
NO_GAMIN_PLATFORMS = ('Darwin',)
NO_KQUEUE_PLATFORMS = ('Linux',)

PLATFORM = platform.system()

TEST_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.abspath(os.path.join(TEST_DIR, 'data'))
TEST_DATA_DIR = os.path.abspath(os.path.join(TEST_DIR, 'test-data'))


class _UnicodePathsMixin(object):
    replacements = {
      'foo': u'ζοο',
      'bar': u'βαρ',
      'baz': u'βαω',
      'qux': u'ςυχ',
      'klink': u'κλινκ',
      'klank': u'κλανκ',
      'klonk': u'κλονκ',
      'klunk': u'κλυνκ',
      'bink': u'βινκ',
      'bonk': u'βονκ',
    }

    def p(self, s):
        s = super(_UnicodePathsMixin, self).p(s)
        for k, v in self.replacements.items():
            s = s.replace(k, v)
        return s


def mixin_unicode(cls):
    newcls = type('%sUnicode' % cls.__name__, (_UnicodePathsMixin, cls), {})
    newcls.__module__ = cls.__module__
    return newcls


def sleep_until(predicate, timeout = 10):
    count = 0
    while not predicate():
        time.sleep(1)
        count = count + 1
        if count > timeout:
            raise AssertionError('timeout reached')


class TestCase(_TestCase):
    def assertIn(self, candidate, collection):
        if not candidate in collection:
            raise AssertionError('%s not in %s' % (
              repr(candidate), repr(collection)))


class TestThatUsesRealFiles(TestCase):
    def _create_file(self, filename, content = ''):
        self._set_file_content(filename, content)

    def _set_file_content(self, filename, content):
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        f = open(filename, 'w')
        try:
            f.write(content)
        finally:
            f.close()

    def _get_file_content(self, filename):
        f = open(filename, 'r')
        try:
            return f.read().decode('utf-8')
        finally:
            f.close()

    def _create_files(self, filenames, contents = None):
        if contents is None:
            contents = ['' for filename in filenames]
        for filename, content in zip(filenames, contents):
            self._create_file(filename, content)

    def _remove_file(self, filename):
        os.unlink(filename)

    def _remove_files(self, filenames):
        for filename in filenames:
            self._remove_file(filename)

    def _create_dir(self, dirname):
        os.mkdir(dirname)

    def _create_dirs(self, dirnames):
        for dirname in dirnames:
            self._create_dir(dirname)

    def _create_dir_if_not_exists(self, dirname):
        try:
            os.mkdir(dirname)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise

    def _remove_dir(self, dirname):
        os.rmdir(dirname)

    def _remove_dirs(self, dirnames):
        for dirname in dirnames:
            self._remove_dir(dirname)

    def _remove_dir_if_empty(self, dirname):
        try:
            os.rmdir(dirname)
        except OSError, e:
            if e.errno != errno.ENOTEMPTY:
                raise

    def assertFileExists(self, filename, mode = 'r'):
        try:
            f = open(filename, mode)
        except (OSError, IOError), e:
            raise AssertionError(str(e))
        else:
            f.close()

    def assertFileDoesNotExist(self, filename, mode = 'r'):
        def test_fn():
            f = open(filename, mode)
            f.close()
        self.assertRaises(IOError, test_fn)

    def assertFileContent(self, filename, expected, mode = 'r'):
        f = open(filename, mode)
        try:
            actual = f.read().decode('utf-8', 'replace')
        finally:
            f.close()
        assert (actual == expected), (
          u'Expected: %s\nGot: %s' % (repr(expected), repr(actual))
        )

    def assertFileContains(self, filename, s, mode = 'r'):
        f = open(filename, mode)
        try:
            content = f.read().decode('utf-8', 'replace')
        finally:
            f.close()
        assert (s in content), (
          u'Expected to find %r in file %r.' % (s, filename)
        )

    def assertFileDoesNotContain(self, filename, s, mode = 'r'):
        f = open(filename, mode)
        try:
            content = f.read().decode('utf-8', 'replace')
        finally:
            f.close()
        assert (s not in content), (
          u'Expected not to find %r in file %r.' % (s, filename)
        )

    def _assertFilePredicate(self, filename1, filename2, predicate, mode = 'r'):
        f1 = open(filename1, mode)
        try:
            f2 = open(filename2, mode)
            try:
                assert predicate(f1, f2)
            finally:
                f2.close()
        finally:
            f1.close()

    def assertFilesAreSame(self, filename1, filename2):
        self._assertFilePredicate(
          filename1, filename2, (lambda f1, f2: f1.read() == f2.read()))

    def assertFilesAreDifferent(self, filename1, filename2):
        self._assertFilePredicate(
          filename1, filename2, (lambda f1, f2: f1.read() != f2.read()))

    def assertDirectoryExists(self, dirname):
        try:
            os.listdir(dirname)
        except (IOError, OSError), e:
            raise AssertionError(unicode(e))

    def assertDirectoryDoesNotExist(self, dirname):
        def test_fn():
            os.listdir(dirname)
        self.assertRaises((IOError, OSError), test_fn)


class TestWithDir(TestThatUsesRealFiles):
    test_dir = None
    test_dir_prefix = None

    def setUp(self):
        self._create_dir_if_not_exists(TEST_DATA_DIR)
        self.test_dir = self._get_next_test_dir()
        os.mkdir(self.test_dir)

    def tearDown(self):
        self._remove_dir(self.test_dir)
        self._remove_dir_if_empty(TEST_DATA_DIR)

    def _get_next_test_dir(self):
        num = 1

        existing_test_dirs = glob.glob(os.path.join(
          TEST_DATA_DIR,
          '%s-[0-9][0-9][0-9]' % self.test_dir_prefix,
        ))
        existing_test_dirs.sort()
        if existing_test_dirs != []:
            num = int(existing_test_dirs[-1][-3:]) + 1
        return unicode(os.path.join(
          TEST_DATA_DIR,
          '%s-%03u' % (self.test_dir_prefix, num),
        ))
