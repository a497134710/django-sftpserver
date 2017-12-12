# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import os
import six
import hashlib
import bsdiff4
import stat as _stat
import time as _time
import yaml

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import models
from future.utils import python_2_unicode_compatible
from django.utils.module_loading import import_string
from django.core.files.storage import default_storage

from django.utils.encoding import force_bytes


def _timestamp(dt):
    if dt is None:
        return 0
    elif hasattr(dt, 'timestamp'):
        return dt.timestamp()
    return _time.mktime(dt.timetuple())


@python_2_unicode_compatible
class AuthorizedKey(models.Model):
    name = models.CharField(max_length=256, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key_type = models.CharField(max_length=32)
    key = models.CharField(max_length=512)
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = (('user', 'name', ))

    def __str__(self):
        return 'AuthorizedKey({})'.format(self.name)


@python_2_unicode_compatible
class Root(models.Model):
    name = models.CharField(max_length=256)
    branch = models.CharField(max_length=256, blank=True, null=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    groups = models.ManyToManyField(Group, blank=True)
    base_commit = models.ForeignKey("Commit", blank=True, null=True,
                                    on_delete=models.SET_NULL, related_name='+')

    class Meta:
        unique_together = (('name', 'branch', ))

    def __str__(self):
        branch = ''
        if self.branch:
            branch = '-' + self.branch
        return 'root({}{})'.format(self.name, branch)

    def has_permission(self, user):
        return bool(user in self.users.all())

    def ls(self, path):
        if path != '/' and path.endswith('/'):
            path = path[:-1]
        if path == '/' and not self.exists(path):
            self.mkdir(path)
        fileobj = self.get(path)
        return MetaFile.objects.filter(parent=fileobj)

    def exists(self, path):
        return MetaFile.objects.filter(root=self, path=path).exists()

    def get(self, path):
        if path != '/' and path.endswith('/'):
            path = path[:-1]
        return MetaFile.objects.get(root=self, path=path)

    def create(self, path):
        dirname, basename = os.path.split(path)
        parent = self.mkdir_if_not_exists(dirname)
        fileobj = MetaFile.objects.create(
            root=self, parent=parent, path=path, filename=basename)
        fileobj.data = b''
        fileobj.save()
        return fileobj

    def put(self, path, content=b''):
        dirname, basename = os.path.split(path)
        parent = self.mkdir_if_not_exists(dirname)
        fileobj, created = MetaFile.objects.get_or_create(
            root=self, parent=parent, path=path, filename=basename)
        if not created and fileobj.key is None:
            raise Exception()
        fileobj.data = content
        fileobj.save()
        return fileobj

    def stat(self, path):
        fileobj = self.get(path)
        return fileobj.stat

    def remove(self, path):
        fileobj = self.get(path)
        fileobj.delete()

    def rename(self, oldpath, newpath):
        fileobj = self.get(oldpath)
        if newpath == '/':
            raise Exception()

        if newpath.endswith('/'):
            newpath = newpath[:-1]
        newdirname, newbasename = os.path.split(newpath)
        fileobj.parent = self.mkdir_if_not_exists(newdirname)
        fileobj.filename = newbasename
        fileobj.update_path()
        return fileobj

    def mkdir(self, path):
        if MetaFile.objects.filter(root=self, path=path).exists():
            raise Exception()
        return self.mkdir_if_not_exists(path)

    def mkdir_if_not_exists(self, path):
        qs = MetaFile.objects.filter(root=self, path=path)
        if qs.exists():
            return qs[0]

        if path == '/':
            return MetaFile.objects.create(root=self, filename='', path=path)

        if path.endswith('/'):
            path = path[:-1]
        dirname, basename = os.path.split(path)
        parent = self.mkdir_if_not_exists(dirname)
        return MetaFile.objects.create(root=self, parent=parent, filename=basename, path=path)

    @property
    def dirty(self):
        if not self.base_commit:
            return True
        commit_items = {x.path: x.key
                        for x in CommitItem.objects.filter(commit=self.base_commit)}
        for item in MetaFile.objects.filter(root=self).order_by("path"):
            value = commit_items.pop(item.path, False)
            if value is not item.key:
                return True
        return bool(commit_items)

    def commit(self):
        c = Commit.objects.create(root=self, parent_commit=self.base_commit)
        self.base_commit = c
        self.save()

        h = hashlib.sha1('{}'.format(_timestamp(c.created_at)).encode('UTF-8'))
        for item in MetaFile.objects.filter(root=self).order_by("path"):
            CommitItem.objects.create(commit=c, path=item.path, key=item.key)
            h.update(item.path.encode('UTF-8'))
            if item.key:
                h.update(item.key.encode('UTF-8'))
        c.key = h.hexdigest()
        c.save()
        return c


class MetaFileMixin(object):
    @property
    def size(self):
        key = '{}_size'.format(self.key)
        value = cache.get(key)
        if value is None:
            value = Data.objects.get(key=self.key).size
        cache.set(key, value, None)
        return value

    @property
    def modified_at(self):
        if self.key is None:
            return self.created_at
        return Data.objects.get(key=self.key).created_at

    @property
    def data(self):
        return Data.get(self.key)

    @data.setter
    def data(self, value):
        self.key = Data.put(value, self.key)


@python_2_unicode_compatible
class MetaFile(MetaFileMixin, models.Model):
    class Stat(object):
        pass

    root = models.ForeignKey(Root, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, blank=True, null=True)
    path = models.CharField(max_length=4096)
    filename = models.CharField(max_length=1024)
    key = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    accessed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = (('root', 'path'))

    def __str__(self):
        return 'MetaFile({})'.format(self.path)

    @property
    def isdir(self):
        return self.key is None

    @property
    def stat(self):
        s = self.Stat()
        s.st_size = 0 if self.isdir else self.size
        s.st_uid = 0
        s.st_gid = 0
        s.st_mode = _stat.S_IFDIR if self.isdir else _stat.S_IFREG
        s.st_mode |= _stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IRGRP | _stat.S_IWGRP
        if self.isdir:
            s.st_mode |= _stat.S_IXUSR | _stat.S_IXGRP
        s.st_atime = _timestamp(self.accessed_at)
        s.st_mtime = _timestamp(self.modified_at)
        return s

    def update_path(self):
        self.path = os.path.join(self.parent.path, self.filename)
        self.save()
        for i in MetaFile.objects.filter(parent=self):
            i.update_path()


@python_2_unicode_compatible
class Data(models.Model):
    key = models.CharField(max_length=40, unique=True)
    parent_key = models.CharField(max_length=40, blank=True, null=True)
    size = models.IntegerField(blank=True, null=True)
    data = models.BinaryField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return 'Data({})'.format(self.key)

    @classmethod
    def get(klass, key):
        value = cache.get(key)
        if value:
            return value
        o = klass.objects.get(key=key)
        if o.parent_key is None:
            value = force_bytes(o.data)
        else:
            parent_data = klass.get(o.parent_key)
            value = klass._merge(parent_data, o.data)
        cache.set(key, force_bytes(value), None)
        return value

    @classmethod
    def put(klass, value, parent_key=None):
        if not isinstance(value, six.binary_type):
            raise TypeError("data type must be binary_type")
        if len(value) > 100 * 1024 * 1024:
            raise Exception("file size exceed")
        key = hashlib.sha1(value).hexdigest()
        cache.set(key, force_bytes(value), None)
        size = len(value)
        if not klass.objects.filter(key=key).exists():
            if parent_key:
                parent_data = klass.get(key=parent_key)
                patch = bsdiff4.diff(parent_data, value)
                if len(value) > 512 and 2 * len(patch) < len(value):
                    value = patch
                else:
                    parent_key = None

            klass.objects.create(key=key, parent_key=parent_key, data=value, size=size)
        return key

    @classmethod
    def _merge(klass, parent_data, current_data):
        return bsdiff4.patch(parent_data, current_data)


@python_2_unicode_compatible
class Commit(models.Model):
    name = models.CharField(max_length=256, blank=True, null=True)
    comment = models.TextField()

    creator = models.ForeignKey(settings.AUTH_USER_MODEL,
                                blank=True, null=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    root = models.ForeignKey(Root, on_delete=models.PROTECT)
    key = models.CharField(max_length=40, blank=True, null=True)

    parent_commit = models.ForeignKey("self", blank=True, null=True,
                                      on_delete=models.PROTECT, related_name='children')
    merge_commit = models.ForeignKey("self", blank=True, null=True,
                                     on_delete=models.PROTECT, related_name='merge_destinations')

    def __str__(self):
        return 'Commit({})'.format(self.name)


@python_2_unicode_compatible
class CommitItem(MetaFileMixin, models.Model):
    commit = models.ForeignKey(Commit, on_delete=models.CASCADE)
    path = models.CharField(max_length=1024)
    key = models.CharField(max_length=40, blank=True, null=True)

    class Meta:
        unique_together = (('commit', 'path', ))

    def __str__(self):
        return 'CommitItem({})'.format(self.key)


@python_2_unicode_compatible
class StorageAccessInfo(models.Model):
    '''
storages.backends.s3boto.S3BotoStorage

access_key: AKIAAAAAAAAAAAAAAAAA
secret_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
bucket_name: s3-test
host: s3-us-west-2.amazonaws.com
default_acl: private
location: test_sftp
url_protocol: https
    '''
    name = models.CharField(max_length=256, unique=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    groups = models.ManyToManyField(Group, blank=True)
    storage_class = models.CharField(max_length=256, blank=True, null=True)
    args = models.TextField(blank=True, null=True)
    kwargs = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def get_storage(self):
        if not self.storage_class:
            return default_storage
        Storage = import_string(self.storage_class)
        args = yaml.load(self.args) if self.args else ()
        kwargs = yaml.load(self.kwargs) if self.kwargs else {}
        return Storage(*args, **kwargs)

    def has_permission(self, user):
        return bool(user in self.users.all())
