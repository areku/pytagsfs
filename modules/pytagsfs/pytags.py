# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

# Import locale from sclapp before all other imports to work around bug in
# stdlib.
# See http://www.selenic.com/mercurial/wiki/index.cgi/Character_Encoding_On_OSX.
from sclapp import locale

import sys, os

from optparse import OptionParser, OptionValueError

import sclapp
from sclapp import CriticalError

from pytagsfs.subspat import SubstitutionPattern, Error as PatternError
from pytagsfs.values import Values
from pytagsfs.metastore.mutagen_ import MutagenFileMetaStore
from pytagsfs.fs import PyTagsFileSystem
from pytagsfs import __version__ as version


def print_tags(meta_store, filenames):
    failed_filenames = []
    for filename in filenames:
        print filename

        try:
            values = meta_store.get(filename)
        except Exception, e:
            sclapp.printCritical(unicode(e))
            failed_filenames.append(filename)
            print
            continue

        for k, v in values.items():
            print '%s: %s' % (k, ', '.join(v))
        print

    if failed_filenames:
        return 1
    return 0


def apply_substitution_pattern(filename, values, substitution_pattern):
    if substitution_pattern:
        splitter = substitution_pattern.get_splitter(values)
        values.update(Values.from_flat_dict(splitter.split(filename)))


def apply_operations(values, operations):
    for opname, arg in operations:
        if opname == 'add':
            name, value = arg.split('=')
            values[name] = values.get(name, []) + [value]
        elif opname == 'set':
            name, value = arg.split('=')
            values[name] = [value]
        elif opname == 'remove':
            try:
                del values[arg]
            except KeyError:
                sclapp.printWarning(u'No such tag: %s' % arg)


def update_tags(meta_store, format, operations, filenames):
    substitution_pattern = None
    if format:
        substitution_pattern = SubstitutionPattern(format)

    failed_filenames = []

    for filename in filenames:
        print filename

        try:
            values = meta_store.get(filename)
        # An error opening the file would likely cause an OSError or IOError,
        # so we catch both here and handle it as such.
        except (OSError, IOError), e:
            sclapp.printCritical(unicode(e))
            failed_filenames.append(filename)
            continue

        new_values = Values(values)

        try:
            apply_substitution_pattern(filename, new_values, substitution_pattern)
        except PatternError, e:
            sclapp.printCritical(unicode(e))
            failed_filenames.append(filename)
            continue

        apply_operations(new_values, operations)

        changes = Values.diff2(values, new_values)

        try:
            meta_store.set(filename, changes)
        # An error opening the file would likely cause an OSError or IOError,
        # so we catch both here and handle it as such.
        except (OSError, IOError), e:
            sclapp.printCritical(unicode(e))
            failed_filenames.append(filename)
            continue

    if failed_filenames:
        sclapp.printCritical('Failed to process the following files:')
    for filename in failed_filenames:
        sclapp.printCritical(filename)

    if failed_filenames:
        return 1
    return 0


def parse_set_values(set_exprs):
    set_values = {}
    for expr in set_exprs:
        try:
            k, v = expr.split('=')
        except (TypeError, ValueError):
            raise CriticalError(1, 'Invalid set expression: %s' % expr)
        set_values[k] = v
    return set_values


class PyTagsOptionParser(OptionParser):
    def __init__(self):
        OptionParser.__init__(
          self,
          usage = '%prog [options] {file} [file...]',
          version = '%%prog version %s' % version,
        )

        self.defaults['operations'] = []

        self.add_option(
          '--format',
          action = 'callback',
          type = 'str',
          callback = self.cb_set_format,
          help = (
            'tag files using meta-data parsed from filenames according to PATTERN; '
            'see the manual page for more information.'
          ),
        )
        self.add_option(
          '--set',
          action = 'callback',
          type = 'str',
          callback = self.cb_append_operation,
          metavar = 'FOO=BAR',
          help = 'set tag named FOO to value BAR',
        )
        self.add_option(
          '--remove',
          action = 'callback',
          type = 'str',
          callback = self.cb_append_operation,
          metavar = 'FOO',
          help = 'unset tag named FOO',
        )
        self.add_option(
          '--add',
          action = 'callback',
          type = 'str',
          callback = self.cb_append_operation,
          metavar = 'FOO=BAR',
          help = 'add value BAR as new value for tag FOO',
        )
        self.add_option(
          '--metastores',
          action = 'store',
          dest = 'metastores',
          default = 'pytagsfs.metastore.mutagen_.MutagenFileMetaStore',
          type = 'str',
          metavar = 'FOO[;BAR...]',
          help = 'select the metastore(s) FOO and BAR',
        )

    def cb_set_format(self, option, opt_str, value, parser):
        if parser.values.operations:
            raise OptionValueError("--format must be specified first")
        setattr(parser.values, option.dest, value)

    def cb_append_operation(self, option, opt_str, value, parser):
        parser.values.operations.append((opt_str.lstrip('-'), value))


@sclapp.main_function
def main(argv):
    parser = PyTagsOptionParser()
    values, args = parser.parse_args(argv[1:])

    if len(args) < 1:
        raise CriticalError(1, 'Too few arguments.')

    meta_store = PyTagsFileSystem.get_meta_store(values.metastores)

    if not (values.format or values.operations):
        return print_tags(meta_store, args)
    else:
        return update_tags(meta_store, values.format, values.operations, args)
