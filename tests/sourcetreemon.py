# Copyright (c) 2007-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, time, stat

from pytagsfs.exceptions import (
  NotADirectory,
  WatchExistsError,
  NoSuchWatchError,
)

from pytagsfs.sourcetreemon.inotifyx_ import (
  InotifyxSourceTreeMonitor,
  DeferredInotifyxSourceTreeMonitor,
)

from pytagsfs.sourcetreemon.gamin_ import (
  GaminSourceTreeMonitor,
  DeferredGaminSourceTreeMonitor,
)

from pytagsfs.sourcetreemon.kqueue_ import (
  KqueueSourceTreeMonitor,
  DeferredKqueueSourceTreeMonitor,
)

from common import (
  PLATFORM,
  NO_INOTIFY_PLATFORMS,
  NO_GAMIN_PLATFORMS,
  NO_KQUEUE_PLATFORMS,
  TEST_DATA_DIR,
  TestWithDir,
)
from manager import manager


ADD = 'ADD'
REMOVE = 'REMOVE'
UPDATE = 'UPDATE'


class StopLooking(Exception):
    pass


class _SourceTreeMonitorTestCase(TestWithDir):
    test_dir_prefix = 'stm'

    sourcetreemoncls = None
    sets_is_dir = False

    def setUp(self):
        super(_SourceTreeMonitorTestCase, self).setUp()

        self.events = []
        self.stm = self.sourcetreemoncls()

        self.stm.set_add_cb(self.add_cb)
        self.stm.set_remove_cb(self.remove_cb)
        self.stm.set_update_cb(self.update_cb)

        self.stm.start()
        self.stm.add_source_dir(self.test_dir)

        # FIXME: Is this necessary?
        time.sleep(2)

    def tearDown(self):
        self.stm.stop()
        del self.stm
        super(_SourceTreeMonitorTestCase, self).tearDown()

    def add_cb(self, path, is_dir = None):
        self.events.append((ADD, path, is_dir))

        try:
            names = os.listdir(path)
        except (IOError, OSError):
            names = []

        try:
            if is_dir is None:
                try:
                    self.stm.add_source_dir(path)
                except NotADirectory:
                    self.stm.add_source_file(path)
            elif is_dir:
                self.stm.add_source_dir(path)
            else:
                self.stm.add_source_file(path)
        except WatchExistsError:
            pass

        for name in names:
            self.stm.add_cb(os.path.join(path, name))

    def remove_cb(self, path, is_dir = None):
        self.events.append((REMOVE, path, is_dir))

        if is_dir is None:
            try:
                self.stm.remove_source_dir(path)
            except NoSuchWatchError:
                self.stm.remove_source_file(path)
        elif is_dir:
            self.stm.remove_source_dir(path)
        else:
            self.stm.remove_source_file(path)

    def update_cb(self, path, is_dir = None):
        self.events.append((UPDATE, path, is_dir))

    def clearEvents(self):
        while self.events:
            self.events.pop()

    def waitForEvents(self, *expected_events, **kwargs):
        expected_events = list(expected_events)

        expect_is_dir = kwargs.get('expect_is_dir', True)

        try:
            for count in range(10):
                self.clearEvents()

                self.stm.process_events()

                for event in self.events:
                    for expected_event in expected_events:
                        if expect_is_dir and self.sets_is_dir:
                            if event == expected_event:
                                expected_events.remove(expected_event)
                                if not expected_events:
                                    raise StopLooking
                        else:
                            if event[0:2] == expected_event[0:2]:
                                expected_events.remove(expected_event)
                                if not expected_events:
                                    raise StopLooking

                time.sleep(1)
        except StopLooking:
            pass

        if expected_events:
            raise AssertionError(
              'did not receive events: %s' % str(expected_events))

    def writeFileContents(self, filename, contents):
        f = open(filename, 'w')
        try:
            f.write(contents)
        finally:
            f.close()

    def test_create_file(self):
        test_file = os.path.join(self.test_dir, 'foo')

        self.writeFileContents(test_file, 'foo\n')

        try:
            self.waitForEvents((ADD, test_file, False))
        finally:
            os.unlink(test_file)

    def test_create_directory(self):
        test_dir = os.path.join(self.test_dir, 'foo')

        os.mkdir(test_dir)

        try:
            self.waitForEvents((ADD, test_dir, True))
        finally:
            os.rmdir(test_dir)

    def test_remove_file(self):
        test_file = os.path.join(self.test_dir, 'foo')

        self.writeFileContents(test_file, 'foo\n')

        try:
            self.waitForEvents((ADD, test_file, False))
        except:
            os.unlink(test_file)
            raise

        os.unlink(test_file)
        self.waitForEvents((REMOVE, test_file, False))

    def test_remove_directory(self):
        test_dir = os.path.join(self.test_dir, 'foo')
        os.mkdir(test_dir)

        try:
            self.waitForEvents((ADD, test_dir, True))
        except:
            os.rmdir(test_dir)
            raise

        os.rmdir(test_dir)
        self.waitForEvents((REMOVE, test_dir, True))

    def test_rename_file(self):
        test_file = os.path.join(self.test_dir, 'foo')
        test_file_renamed = os.path.join(self.test_dir, 'bar')

        self.writeFileContents(test_file, 'foo\n')

        try:
            self.waitForEvents((ADD, test_file, False))
        except:
            os.unlink(test_file)
            raise

        os.rename(test_file, test_file_renamed)

        try:
            self.waitForEvents(
              (REMOVE, test_file, False),
              (ADD, test_file_renamed, False),
            )
        finally:
            os.unlink(test_file_renamed)

    def test_rename_directory(self):
        test_dir = os.path.join(self.test_dir, 'foo')
        test_dir_renamed = os.path.join(self.test_dir, 'bar')

        os.mkdir(test_dir)

        try:
            self.waitForEvents((ADD, test_dir, True))
        except:
            os.rmdir(test_dir)
            raise

        os.rename(test_dir, test_dir_renamed)

        try:
            self.waitForEvents(
              (REMOVE, test_dir, True),
              (ADD, test_dir_renamed, True),
            )
        finally:
            os.rmdir(test_dir_renamed)

    def test_update_file(self):
        test_file = os.path.join(self.test_dir, 'foo')

        self.writeFileContents(test_file, 'foo\n')

        try:
            self.waitForEvents((ADD, test_file, False))
        except:
            os.unlink(test_file)
            raise

        f = open(test_file, 'a+')
        try:
            f.write('bar\n')
        finally:
            f.close()

        try:
            self.waitForEvents((UPDATE, test_file, False))
        finally:
            os.unlink(test_file)

    def test_replace_file(self):
        test_file = os.path.join(self.test_dir, 'foo')
        replacement_source_file = 'bar'

        self.writeFileContents(test_file, 'foo\n')

        try:
            self.waitForEvents((ADD, test_file, False))
        except:
            os.unlink(test_file)
            raise

        self.writeFileContents(replacement_source_file, 'bar\n')
        os.rename(replacement_source_file, test_file)

        try:
            self.waitForEvents(
              # On replacements, we need not receive a remove event.  Some
              # SourceTreeMonitor implementations do not provide this easily,
              # and SourceTreeRepresentation does an update when a path is added
              # twice, anyway.
              #(REMOVE, test_file, False),
              (ADD, test_file, False),
            )
        finally:
            os.unlink(test_file)

    def test_remove_nested_directories(self):
        test_dir_base = os.path.join(self.test_dir, 'a')
        test_dir = os.path.join(test_dir_base, 'b', 'c', 'd', 'e', 'f')

        dirs = []
        dir = test_dir
        while dir != self.test_dir:
            dirs.append(dir)
            dir = os.path.dirname(dir)

        def remove_dirs():
            for dir in dirs:
                os.rmdir(dir)

        os.makedirs(test_dir)
        try:
            self.waitForEvents((ADD, test_dir, True), expect_is_dir = False)
        except:
            remove_dirs()
            raise

        remove_dirs()

        # Test that removals are received in the right order for nested
        # directories:

        removals = []
        count = 0

        while len(removals) < len(dirs):
            self.stm.process_events()

            while self.events:
                event = self.events.pop(0)
                if event[0] == REMOVE:
                    removals.append(event[1])
            time.sleep(1)
            count = count + 1

            if count > len(dirs) + 1:
                raise AssertionError('waited too long for events')

        self._check_removals(removals, dirs)

    def _check_removals(self, removals, dirs):
        self.assertEqual(removals, dirs)


if PLATFORM not in NO_INOTIFY_PLATFORMS:
    class InotifyxSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = InotifyxSourceTreeMonitor
        sets_is_dir = True

    manager.add_test_case_class(InotifyxSourceTreeMonitorTestCase)

    class DeferredInotifyxSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = DeferredInotifyxSourceTreeMonitor
        sets_is_dir = True

    manager.add_test_case_class(DeferredInotifyxSourceTreeMonitorTestCase)


if PLATFORM not in NO_GAMIN_PLATFORMS:
    class GaminSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = GaminSourceTreeMonitor
        sets_is_dir = False

        def _check_removals(self, removals, dirs):
            # Gamin does not return these events in a reliable order.  This
            # situation is handled fine, even though it is inappropriate.  As
            # an exception, we don't fail this test if that happens.
            self.assertEqual(set(removals), set(dirs))

    manager.add_test_case_class(GaminSourceTreeMonitorTestCase)

    class DeferredGaminSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = DeferredGaminSourceTreeMonitor
        sets_is_dir = False

        def _check_removals(self, removals, dirs):
            # Gamin does not return these events in a reliable order.  This
            # situation is handled fine, even though it is inappropriate.  As
            # an exception, we don't fail this test if that happens.
            self.assertEqual(set(removals), set(dirs))

    manager.add_test_case_class(DeferredGaminSourceTreeMonitorTestCase)


if PLATFORM not in NO_KQUEUE_PLATFORMS:
    class KqueueSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = KqueueSourceTreeMonitor
        sets_is_dir = False

    manager.add_test_case_class(KqueueSourceTreeMonitorTestCase)

    class DeferredKqueueSourceTreeMonitorTestCase(_SourceTreeMonitorTestCase):
        sourcetreemoncls = DeferredKqueueSourceTreeMonitor
        sets_is_dir = False

    manager.add_test_case_class(DeferredKqueueSourceTreeMonitorTestCase)
