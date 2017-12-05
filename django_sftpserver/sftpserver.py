# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import io
import os
import paramiko
import stat as _stat

from django.contrib.auth import get_user_model
from . import models


class StubServer(paramiko.ServerInterface):

    def set_username(self, username):
        root, branch = None, None
        if ':' in username:
            username, root = username.split(':')
            if '/' in root:
                root, branch = root.split('/')
        self.username = username
        self.user = get_user_model().objects.get(username=username)
        self.root_name = root
        self.branch_name = branch
        if self.root_name:
            self.root = models.Root.objects.get(
                name=self.root_name, branch=self.branch_name)
        else:
            self.root = None

    def check_auth_publickey(self, username, key):
        try:
            self.set_username(username)
        except get_user_model().DoesNotExist:
            return paramiko.AUTH_FAILED
        except models.Root.DoesNotExist:
            return paramiko.AUTH_FAILED

        if self.root and (not self.root.has_permission(self.user)):
            return paramiko.AUTH_FAILED

        for public_key in models.AuthorizedKey.objects.filter(user=self.user):
            if key.get_base64() == public_key.key:
                return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        print('kind={} => channelid={} channel_request success!!'.format(kind, chanid))
        return paramiko.OPEN_SUCCEEDED

    def get_allowed_auths(self, username):
        return "publickey"


class StubSFTPHandle(paramiko.SFTPHandle):

    def __init__(self, server, root, path, flags):
        super(StubSFTPHandle, self).__init__(flags)
        self._fileobj = root.get(path)
        self._bytesio = io.BytesIO(self._fileobj.data)
        # 'ab', 'wb', 'a+b', 'r+b', 'rb'
        self._read_only = False
        if flags & os.O_WRONLY:
            if flags & os.O_APPEND:
                self._bytesio.seek(self._fileobj.size)
            else:
                self._bytesio.seek(0)
        elif flags & os.O_RDWR:
            if flags & os.O_APPEND:
                self._bytesio.seek(self._fileobj.size)
            else:
                self._bytesio.seek(0)
        else:  # O_RDONLY (== 0)
            self._read_only = True
            self._bytesio.seek(0)
        # self.filename = path
        self._modified = False
        self.readfile = self._bytesio
        self.writefile = self._bytesio

    def close(self):
        if (not self._read_only) and self._modified:
            self._fileobj.data = self._bytesio.getvalue()
            self._fileobj.save()
        super(StubSFTPHandle, self).close()

    def write(self, offset, data):
        self._modified = True
        return super(StubSFTPHandle, self).write(offset, data)

    def stat(self):
        return paramiko.SFTPAttributes.from_stat(self.fileobj.stat)

    def chattr(self, attr):
        return paramiko.SFTP_OP_UNSUPPORTED


class StubSFTPServer(paramiko.SFTPServerInterface):

    def __init__(self, server, *largs, **kwargs):
        super(StubSFTPServer, self).__init__(server, *largs, **kwargs)
        self.server = server
        self.user = self.server.user
        self.root = self.server.root
        print("initialized")

    def session_started(self):
        print("started")
        pass

    def session_ended(self):
        print("session ended")
        self.server = None

    def _resolve(self, path):
        print("resolve", path)
        if self.root:
            return self.root, path
        else:
            l = path.split(os.path.sep)
            if l[1]:
                return None, '/'
            else:
                r = models.Root.objects.get(name=l[1])
                return r, '/' + os.path.sep.join(l[2:])

    def list_folder(self, path):
        root, path = self._resolve(path)
        result = []
        if root is None:
            for r in models.Root.objects.all():
                if not r.has_permission(self.user):
                    continue
                attr = paramiko.SFTPAttributes.from_stat()
                attr.filename = r.name
                attr.st_size = 0
                attr.st_uid = 0
                attr.st_gid = 0
                attr.st_mode = _stat.S_IFDIR | 0x550
                attr.st_atime = 0
                attr.st_mtime = 0
                result.append(attr)
        else:
            for fobj in root.ls(path):
                attr = paramiko.SFTPAttributes.from_stat(fobj.stat)
                attr.filename = fobj.filename
                result.append(attr)
        print('list', path, result)
        return result

    def stat(self, path):
        print('stat', path)
        root, path = self._resolve(path)
        return paramiko.SFTPAttributes.from_stat(root.get(path).stat)

    def lstat(self, path):
        print('lstat', path)
        return self.stat(path)

    def open(self, path, flags, attr):
        print('open', path)
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        if (not (flags & os.O_WRONLY)) and (
                not ((flags & os.O_RDWR) and (flags & os.O_APPEND))):
            if not root.exists(path):
                return paramiko.SFTP_NO_SUCH_FILE
        if not root.exists(path):
            root.create(path)
        return StubSFTPHandle(self, root, path, flags)

    def remove(self, path):
        print("remove", path)
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.remove(path)

    def rename(self, oldpath, newpath):
        print("rnemae", oldpath, newpath)
        oldroot, oldpath = self._resolve(oldpath)
        newroot, newpath = self._resolve(newpath)
        if oldroot != newroot:
            return paramiko.SFTP_OP_UNSUPPORTED
        else:
            oldroot.rename(oldpath, newpath)
        return paramiko.SFTP_OK

    def mkdir(self, path, attr):
        print("mkdir", path)
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.mkdir(path)
        return paramiko.SFTP_OK

    def rmdir(self, path):
        print("rmdir", path)
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.remove(path)
        return paramiko.SFTP_OK

    def chattr(self, path, attr):
        print("chattr", path, attr)
        return paramiko.SFTP_OK
        # return paramiko.SFTP_OP_UNSUPPORTED

    def symlink(self, target_path, path):
        print("symlink", target_path, path)
        return paramiko.SFTP_OK
        # return paramiko.SFTP_OP_UNSUPPORTED

    def readlink(self, path):
        print("readlink", path)
        return paramiko.SFTP_OK
        # return paramiko.SFTP_OP_UNSUPPORTED
