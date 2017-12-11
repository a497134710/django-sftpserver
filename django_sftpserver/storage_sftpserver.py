# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import os
import logging
import paramiko
import stat as _stat
import time as _time

from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from . import models

logger = logging.getLogger(__name__)


def _log_error(f):
    def wrapper(*args, **kwargs):
        try:
            # return f(*args, **kwargs)
            retval = f(*args, **kwargs)
            logger.debug("return value : {}".format(retval))
            return retval
        except:
            logger.exception('Unexpected Error')
            raise
    return wrapper


def _timestamp(dt):
    if dt is None:
        return 0
    elif hasattr(dt, 'timestamp'):
        return dt.timestamp()
    return _time.mktime(dt.timetuple())


def _file_attr(storage, path):
    attr = paramiko.SFTPAttributes()
    attr.filename = os.path.basename(path)
    try:
        attr.st_size = storage.size(path)
    except:
        attr.st_size = 0
    attr.st_uid = 0
    attr.st_gid = 0
    directories, files = storage.listdir(os.path.dirname(path))
    logger.debug('check {} : {}, {}'.format(path, directories, files))
    attr.st_mode = ((_stat.S_IFREG if (path and (os.path.basename(path) in files)) else _stat.S_IFDIR) |
                    _stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IXUSR |
                    _stat.S_IRGRP | _stat.S_IWGRP | _stat.S_IXGRP)
    try:
        attr.st_atime = _timestamp(storage.accessed_time(path))
    except:
        attr.st_atime = 0
    try:  # if hasattr(storage, 'modified_time'):
        attr.st_mtime = _timestamp(storage.modified_time(path))
    except:
        attr.st_mtime = 0
    logger.debug('{} : {}'.format(path, attr))
    return attr


def _directory_attr(filename):
    attr = paramiko.SFTPAttributes()
    attr.filename = filename
    attr.st_size = 0
    attr.st_uid = 0
    attr.st_gid = 0
    attr.st_mode = (_stat.S_IFDIR |
                    _stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IXUSR |
                    _stat.S_IRGRP | _stat.S_IWGRP | _stat.S_IXGRP)
    attr.st_atime = 0
    attr.st_mtime = 0
    return attr


class StubServer(paramiko.ServerInterface):

    def __init__(self, addr=None, *args, **kwargs):
        self.client_addr = addr
        super(StubServer, self).__init__(*args, **kwargs)

    def _set_username(self, username):
        storage_name = None
        if '/' in username:
            username = username.split('/')
            if len(username) == 2:
                username, storage_name = username
            else:
                return False
        self.username = username
        self.user = get_user_model().objects.get(username=username)
        self.storage_name = storage_name
        if self.storage_name is None:
            valid_count = 0
            self.storage_access_info = None
            for sai in models.StorageAccessInfo.objects.all():
                if sai.has_permission(self.user):
                    valid_count += 1
            if valid_count == 0:
                return False
            return True
        else:
            self.storage_access_info = models.StorageAccessInfo.objects.get(name=self.storage_name)
        return self.storage_access_info.has_permission(self.user)

    @_log_error
    def check_auth_publickey(self, username, key):
        logger.debug('authenticating {}'.format(username))
        try:
            if not self._set_username(username):
                return paramiko.AUTH_FAILED
        except get_user_model().DoesNotExist:
            return paramiko.AUTH_FAILED
        except models.StorageAccessInfo.DoesNotExist:
            return paramiko.AUTH_FAILED

        for public_key in models.AuthorizedKey.objects.filter(user=self.user):
            if key.get_base64() == public_key.key:
                return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    @_log_error
    def check_channel_request(self, kind, chanid):
        logger.debug('kind={} => channelid={} channel_request success!!'.format(kind, chanid))
        return paramiko.OPEN_SUCCEEDED

    @_log_error
    def get_allowed_auths(self, username):
        return "publickey"


class StubSFTPHandle(paramiko.SFTPHandle):

    @_log_error
    def __init__(self, server, storage, path, flags):
        super(StubSFTPHandle, self).__init__(flags)
        self._storage = storage
        self._path = path
        self._flags = flags
        # 'ab', 'wb', 'a+b', 'r+b', 'rb'
        self._read_only = False
        if flags & os.O_WRONLY:
            if flags & os.O_APPEND:
                fstr = 'ab'
            else:
                fstr = 'wb'
        elif flags & os.O_RDWR:
            if flags & os.O_APPEND:
                fstr = 'a+b'
            else:
                fstr = 'r+b'
        else:  # O_RDONLY (== 0)
            fstr = 'rb'

        fileobj = storage.open(path, fstr)
        self._modified = False
        self.readfile = fileobj
        self.writefile = fileobj

    @_log_error
    def stat(self):
        return _file_attr(self._storage, self._path)

    @_log_error
    def chattr(self, attr):
        return paramiko.SFTP_OP_UNSUPPORTED


class StubSFTPServer(paramiko.SFTPServerInterface):

    @_log_error
    def __init__(self, server, *largs, **kwargs):
        super(StubSFTPServer, self).__init__(server, *largs, **kwargs)
        self.server = server
        self.user = self.server.user
        self.storage = None
        if server.storage_access_info:
            self.storage = server.storage_access_info.get_storage()
        else:
            self.storages = {}
            for sai in models.StorageAccessInfo.objects.all():
                if sai.has_permission(self.user):
                    self.storages[sai.name] = sai.get_storage()
        logger.debug("initialized")

    @_log_error
    def session_started(self):
        logger.debug("started")

    @_log_error
    def session_ended(self):
        logger.debug("session ended")
        self.server = None

    def _resolve(self, path):
        path = self.canonicalize(path)
        if self.storage:
            return self.storage, path[1:]
        else:
            l = path.split(os.path.sep)
            if not l[1]:
                return None, '/'
            else:
                return self.storages[l[1]], os.path.sep.join(l[2:])

    @_log_error
    def list_folder(self, path):
        logger.debug('list folder : {}'.format(path))
        storage, path = self._resolve(path)
        result = []
        if storage is None:
            for storage_name in self.storages:
                result.append(_directory_attr(storage_name))
        else:
            logger.debug('list folder : {} {}'.format(storage, path))
            directories, files = storage.listdir(path)
            for directory in directories:
                if not directory:
                    continue
                result.append(_directory_attr(directory))
            for filename in files:
                if not filename:
                    continue
                result.append(_file_attr(storage, os.path.join(path, filename)))
        return result

    @_log_error
    def stat(self, path):
        logger.debug('stat: {}'.format(path))
        storage, path = self._resolve(path)
        if not storage:
            return _directory_attr('/')
        # TODO
        # if not storage.exists(path):
        #     return paramiko.SFTP_NO_SUCH_FILE
        return _file_attr(storage, path)

    @_log_error
    def lstat(self, path):
        logger.debug('lstat: {}'.format(path))
        return self.stat(path)

    @_log_error
    def open(self, path, flags, attr):
        logger.debug('open: {}'.format(path))
        storage, path = self._resolve(path)
        if not storage:
            return paramiko.SFTP_PERMISSION_DENIED
        if (not (flags & os.O_WRONLY)) and (
                not ((flags & os.O_RDWR) and (flags & os.O_APPEND))):
            if not storage.exists(path):
                return paramiko.SFTP_NO_SUCH_FILE
        if not storage.exists(path):
            storage.save(path, ContentFile(b''))
        return StubSFTPHandle(self, storage, path, flags)

    @_log_error
    def remove(self, path):
        logger.debug("remove: {}".format(path))
        storage, path = self._resolve(path)
        if not storage:
            return paramiko.SFTP_PERMISSION_DENIED
        storage.delete(path)

    @_log_error
    def rename(self, oldpath, newpath):
        logger.debug("rnemae {} -> {}".format(oldpath, newpath))
        oldstorage, oldpath = self._resolve(oldpath)
        newstorage, newpath = self._resolve(newpath)
        src = oldstorage.open(oldpath, 'rb')
        dst = newstorage.open(newpath, 'wb')
        dst.write(src.read())
        dst.close()
        oldstorage.delete(oldpath)
        return paramiko.SFTP_OK

    @_log_error
    def mkdir(self, path, attr):
        logger.debug("mkdir: {}".format(path))
        storage, path = self._resolve(path)
        if not storage:
            return paramiko.SFTP_PERMISSION_DENIED
        if storage.exists(path):
            return paramiko.SFTP_OP_UNSUPPORTED
        storage.save(os.path.join(path, '_'), ContentFile(b''))
        storage.delete(os.path.join(path, '_'))
        return paramiko.SFTP_OK

    @_log_error
    def rmdir(self, path):
        logger.debug("rmdir: {}".format(path))
        storage, path = self._resolve(path)
        if not storage:
            return paramiko.SFTP_PERMISSION_DENIED
        storage.delete(path)
        return paramiko.SFTP_OK

    @_log_error
    def chattr(self, path, attr):
        logger.debug("chattr '{}' '{}'".format(path, attr))
        return paramiko.SFTP_OP_UNSUPPORTED

    @_log_error
    def symlink(self, target_path, path):
        logger.debug("symlink '{}' '{}'".format(target_path, path))
        return paramiko.SFTP_OP_UNSUPPORTED

    @_log_error
    def readlink(self, path):
        logger.debug("readlink '{}'".format(path))
        return paramiko.SFTP_OP_UNSUPPORTED
