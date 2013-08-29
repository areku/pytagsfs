#!/usr/bin/env python

# Author: Forest Bond <forest@alittletooquiet.net>
# This file is in the public domain.

import os, sys, commands
from distutils.command.build import build as _build
from distutils.command.clean import clean as _clean
from distutils.command.build_py import build_py
from distutils.core import setup, Command
from distutils.spawn import spawn
from distutils import log
from distutils.dir_util import remove_tree
from distutils.dist import Distribution

project_dir = os.path.dirname(__file__)
modules_dir = os.path.join(project_dir, 'modules')

sys.path.insert(0, modules_dir)
sys.path.insert(0, project_dir)

from tests.common import TEST_DATA_DIR


################################################################################


class test(Command):
    description = 'run tests'
    user_options = [
      ('tests=', None, 'names of tests to run'),
      ('print-only', None, "don't run tests, just print their names"),
      ('coverage', None, "print coverage analysis (requires coverage.py)"),
    ]

    def initialize_options(self):
        self.tests = None
        self.print_only = False
        self.coverage = False

    def finalize_options(self):
        if self.tests is not None:
            self.tests = self.tests.split(',')

    def run(self):
        from tests import main
        main(
          test_names = self.tests,
          print_only = self.print_only,
          coverage = self.coverage,
        )

################################################################################

class clean(_clean):
    temporary_files = []
    nontemporary_files = []

    temporary_dirs = []
    nontemporary_dirs = []

    def clean_file(self, filename):
        if not os.path.exists(filename):
            log.info("'%s' does not exist -- can't clean it", filename)
            return

        log.info("removing '%s'" % filename)
        if not self.dry_run:
            try:
                os.unlink(filename)
            except (IOError, OSError):
                log.warn("failed to remove '%s'" % filename)

    def clean_dir(self, dirname):
        if not os.path.exists(dirname):
            log.info("'%s' does not exist -- can't clean it", dirname)
            return

        log.info("removing '%s' (and everything under it)" % dirname)
        if not self.dry_run:
            try:
                remove_tree(dirname)
            except (IOError, OSError):
                log.warn("failed to remove '%s'" % dirname)

    def clean_test_data(self):
        from pytagsfs.fs import UMOUNT_COMMAND

        try:
            dirs = os.listdir(TEST_DATA_DIR)
        except (IOError, OSError):
            log.warn(
              "not cleaning '%s': failed to read directory" % TEST_DATA_DIR)
        else:
            for dir in dirs:
                full_dir = os.path.join(TEST_DATA_DIR, dir)
                mnt_dir = os.path.join(full_dir, 'mnt')

                log.info("unmounting '%s'" % mnt_dir)
                status, output = commands.getstatusoutput(
                  UMOUNT_COMMAND % mnt_dir)
                if status != 0:
                    print >>sys.stderr, output

                self.clean_dir(full_dir)

        self.clean_dir(TEST_DATA_DIR)

    def run(self):
        self.clean_test_data()

        remove_files = list(self.temporary_files)
        if self.all:
            remove_files = remove_files + self.nontemporary_files

        for filename in remove_files:
            if callable(filename):
                filename = filename(self.distribution)
            self.clean_file(filename)

        remove_dirs = list(self.temporary_dirs)
        if self.all:
            remove_dirs = remove_dirs + self.nontemporary_dirs

        for dirname in remove_dirs:
            if callable(dirname):
                dirname = dirname(self.distribution)
            self.clean_dir(dirname)

        _clean.run(self)

################################################################################

def find_docbook_manpage_stylesheet():
    from libxml2 import catalogResolveURI
    return catalogResolveURI(
      'http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl'
    )

class build_manpages(Command):
    xsltproc = ['xsltproc', '--nonet', '--novalid', '--xinclude']
    description = 'Build manual pages from docbook XML.'
    user_options = []
    man_build_dir = 'build/man'
    stylesheet = find_docbook_manpage_stylesheet()

    def initialize_options(self):
        pass

    def finalize_options(self):
        if self.distribution.manpage_sources is not None:
            self.docbook_files = [
              os.path.abspath(p) for p in self.distribution.manpage_sources
              if p.endswith('.xml')
            ]

    def build_manpage_from_docbook(self, docbook_file):
        assert self.stylesheet is not None, 'failed to find stylesheet'

        command = self.xsltproc + [self.stylesheet, docbook_file]
        orig_wd = os.getcwd()
        os.chdir(self.man_build_dir)
        try:
            spawn(command, dry_run = self.dry_run)
        finally:
            os.chdir(orig_wd)

    def run(self):
        if self.stylesheet is None:
            log.warn(
              'Warning: missing docbook XSL stylesheets; '
              'manpages will not be built.\n'
              'Please install the docbook XSL stylesheets from '
              'http://docbook.org/.'
            )

        manpage_sources = self.docbook_files
        if manpage_sources:
            if not os.path.exists(self.man_build_dir):
                os.mkdir(self.man_build_dir)
            for docbook_file in self.docbook_files:
                self.build_manpage_from_docbook(docbook_file)

clean.nontemporary_dirs.append('build/man')
Distribution.manpage_sources = None

################################################################################

class build_version_file(build_py):
    def initialize_options(self):
        build_py.initialize_options(self)

        self.version = None
        self.version_file = None

    def finalize_options(self):
        build_py.finalize_options(self)

        self.packages = self.distribution.packages
        self.py_modules = [self.distribution.version_module]

        self.version = self.distribution.get_version()
        self.version_file = self.distribution.version_file

    def check_module(self, *args, **kwargs):
        pass

    def build_modules(self, *args, **kwargs):
        log.info("creating version file '%s'" % self.version_file)
        if not self.dry_run:
            f = open(self.version_file, 'w')
            f.write('version = %s\n' % repr(self.version))
            f.close()
        build_py.build_modules(self, *args, **kwargs)

clean.temporary_files.append(lambda distribution: distribution.version_file)
Distribution.version_module = None
Distribution.release_file = None

def get_bzr_version():
    status, output = commands.getstatusoutput('bzr revno')
    return 'bzr%s' % output.strip()

def get_version(release_file):
    try:
        f = open(release_file, 'r')
        try:
            version = f.read().strip()
        finally:
            f.close()
    except (IOError, OSError):
        version = get_bzr_version()
    return version

def get_version_file(version_module):
    return '%s.py' % os.path.join(
      *(['modules'] + version_module.split('.'))
    )

def wrap_init(fn):
    def __init__(self, *args, **kwargs):
        fn(self, *args, **kwargs)
        self.version_file = get_version_file(self.version_module)
        self.metadata.version = get_version(self.release_file)
    return __init__

Distribution.__init__ = wrap_init(Distribution.__init__)

################################################################################

class build(_build):
    sub_commands = _build.sub_commands + [
      ('build_version_file', (lambda self: True)),
      ('build_manpages', (lambda self: True)),
    ]

################################################################################

data_files = []
manpage_sources = []

if build_manpages.stylesheet is not None:
    manpage_sources = ['pytagsfs.xml', 'pytags.xml']
    manpages = [
      os.path.join(
        'build',
        'man',
        s.replace('xml', '1'),
      )
      for s in manpage_sources
    ]
    data_files.append(('share/man/man1', manpages))

setup(
  cmdclass = {
    'test': test,
    'build': build,
    'build_version_file': build_version_file,
    'build_manpages': build_manpages,
    'clean': clean,
  },
  name = 'pytagsfs',
  version_module = 'pytagsfs.version',
  package_dir = {
    'pytagsfs': os.path.join('modules', 'pytagsfs')
  },
  packages = [
    'pytagsfs',
    'pytagsfs.fs',
    'pytagsfs.metastore',
    'pytagsfs.pathstore',
    'pytagsfs.sourcetreemon',
    'pytagsfs.sourcetreerep',
    'pytagsfs.specialfile',
  ],
  scripts = [
    'pytagsfs',
    'pytags',
  ],
  manpage_sources = manpage_sources,
  release_file = 'release',
  data_files = data_files,
)
