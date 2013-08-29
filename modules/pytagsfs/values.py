# Copyright (c) 2008, 2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from pytagsfs.util import unique


class Values(dict):
    def __init__(self, *args, **kwargs):
        super(Values, self).__init__(*args, **kwargs)
        for k, v in self.items():
            self[k] = list(self[k])

    def __setitem__(self, k, v):
        v = list(v)
        super(Values, self).__setitem__(k, v)

    def __repr__(self):
        return '%s(%s)' % (
          self.__class__.__name__,
          super(Values, self).__repr__(),
        )

    @classmethod
    def from_flat_dict(cls, d):
        result = cls()
        for k, v in d.items():
            if v is None:
                result[k] = []
            else:
                result[k] = [v]
        return result

    @classmethod
    def combine(cls, list_of_values):
        merged = cls()
        for values in list_of_values:
            for k, value in values.items():
                if k in merged:
                    merged[k].extend(value)
                else:
                    merged[k] = list(value)

        for k, l in merged.items():
            merged[k] = list(unique(merged[k]))

        return merged

    @classmethod
    def diff2(cls, old, new):
        difference = cls(new)
        for k, v in old.items():
            if k in difference:
                if set(difference[k]) == set(v):
                    del difference[k]
            else:
                difference[k] = []
        return difference

    @classmethod
    def diff3(cls, base, old, new):
        difference = cls.diff2(old, new)

        merged = cls(base)

        for k in base:
            if k not in difference:
                del merged[k]

        for k in difference:
            if k not in base:
                merged[k] = list(difference[k])
            else:
                base_values = list(base[k])
                old_values = list(old[k])
                difference_values = list(difference[k])

                merged_values = list(base_values)
                for old_value in old_values:
                    try:
                        merged_values.remove(old_value)
                    except ValueError:
                        pass
                merged_values.extend(difference_values)

                merged[k] = merged_values

        return merged

    def to_flat_dict(self):
        d = {}
        for k in self:
            d[k] = self[k][0]
        return d

    def iter_permutations(self):
        copy_self = Values(self)

        if not copy_self:
            yield {}
            return

        key, values = copy_self.popitem()

        for d in copy_self.iter_permutations():
            for value in values:
                d = dict(d)
                d[key] = value
                yield d
