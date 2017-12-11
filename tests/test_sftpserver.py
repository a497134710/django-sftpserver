# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import sys
import os
import uuid
import shutil
import paramiko

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_sftpserver import models, sftpserver, storage_sftpserver

if sys.version_info[0] == 2:
    import backports.unittest_mock
    backports.unittest_mock.install()

from unittest.mock import Mock  # NOQA


class TestDjango_sftpserver_sftpserver(TestCase):
    valid_username = 'user'
    invalid_username = 'user2'
    valid_root_name = 'root'
    valid_root_name_2 = 'root_2'

    def setUp(self):
        self.user = get_user_model().objects.create(username=self.valid_username)
        self.valid_key = Mock()
        self.valid_key.get_name = Mock(return_value='ssh-rsa')
        self.valid_key.get_base64 = Mock(return_value='public_key')
        self.invalid_key = Mock()
        self.invalid_key.get_name = Mock(return_value='ssh-rsa')
        self.invalid_key.get_base64 = Mock(return_value='public_key2')
        models.AuthorizedKey.objects.create(user=self.user, key_type='ssh-rsa', key='public_key')
        root = models.Root.objects.create(name=self.valid_root_name)
        root.users.add(self.user)
        models.Root.objects.create(name=self.valid_root_name_2)

    def test_auth_all(self):
        server = sftpserver.StubServer()
        self.assertEqual(server.check_auth_publickey(self.valid_username, self.valid_key),
                         paramiko.AUTH_SUCCESSFUL)

        self.assertEqual(server.check_auth_publickey(self.valid_username, self.invalid_key),
                         paramiko.AUTH_FAILED)
        self.assertEqual(server.check_auth_publickey(self.invalid_username, self.valid_key),
                         paramiko.AUTH_FAILED)
        self.assertEqual(server.check_auth_publickey(self.invalid_username, self.invalid_key),
                         paramiko.AUTH_FAILED)

    def test_auth_root(self):
        server = sftpserver.StubServer()
        name = '{}/{}'.format(self.valid_username, self.valid_root_name)
        self.assertEqual(server.check_auth_publickey(name, self.valid_key),
                         paramiko.AUTH_SUCCESSFUL)

        name = '{}/{}'.format(self.valid_username, self.valid_root_name_2)
        self.assertEqual(server.check_auth_publickey(name, self.valid_key),
                         paramiko.AUTH_FAILED)

        name = '{}/{}invalid'.format(self.valid_username, self.valid_root_name)
        self.assertEqual(server.check_auth_publickey(name, self.valid_key),
                         paramiko.AUTH_FAILED)

    def test_auth_root_with_branch(self):
        pass


class TestDjango_sftpserver_sftpserver_with_root(TestCase):
    def setUp(self):
        self.root = models.Root.objects.create(name="root_example")
        self.server = sftpserver.StubServer()
        self.server.user = None
        self.server.root = self.root
        self.sftpserver = sftpserver.StubSFTPServer(self.server)
        self.sftpserver.session_started()


class TestDjango_sftpserver_sftpserver_without_root(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="user")
        self.root0 = models.Root.objects.create(name="root0")
        self.root1 = models.Root.objects.create(name="root1")
        self.root2 = models.Root.objects.create(name="root2")
        self.root0.users.add(self.user)
        self.root1.users.add(self.user)
        self.server = sftpserver.StubServer()
        self.server.user = self.user
        self.server.root = None
        self.sftpserver = sftpserver.StubSFTPServer(self.server)
        self.sftpserver.session_started()

    def test_list_folder(self):
        print(self.sftpserver.list_folder('/'))
        print(self.sftpserver.list_folder('/root0'))
        print(self.sftpserver.list_folder('/root1'))
        # print(self.sftpserver.list_folder('/root2'))

    def test_stat(self):
        self.sftpserver.stat('/')
        self.root0.put("/a/b", b"c")
        self.sftpserver.stat('/root0/')
        self.sftpserver.stat('/root0/a')
        self.sftpserver.stat('/root0/a/b')

    def test_open(self):
        self.root0.put("/a/b", b"b")
        self.sftpserver.list_folder('/root0/a')
        self.sftpserver.list_folder('/root0/a/b')
        print(self.sftpserver.open('/root0/a/b', os.O_RDONLY, None).readfile.getvalue())
        self.sftpserver.open('/root0/a/c', os.O_WRONLY, None).write(0, b'c')

    def test_remove(self):
        pass

    def test_rename(self):
        pass

    def test_mkdir(self):
        pass

    def test_rmdir(self):
        pass


class TestDjango_sftpserver_storage_sftpserver_with_root(TestCase):
    storage_root = '/tmp/django_sftpserver_test-{}'.format(uuid.uuid4().hex)

    def setUp(self):
        if os.path.exists(self.storage_root):
            shutil.rmtree(self.storage_root)
        os.mkdir(self.storage_root)

        self.storage_access_info = models.StorageAccessInfo.objects.create(
            name="storage_example",
            storage_class="django.core.files.storage.FileSystemStorage",
            kwargs="location: {}".format(self.storage_root),
        )
        self.server = storage_sftpserver.StubServer()
        self.server.user = None
        self.server.storage_access_info = self.storage_access_info
        self.sftpserver = storage_sftpserver.StubSFTPServer(self.server)
        self.sftpserver.session_started()

    def tearDown(self):
        if os.path.exists(self.storage_root):
            shutil.rmtree(self.storage_root)

    def test_list_folder(self):
        print([x.filename for x in self.sftpserver.list_folder("/")])
