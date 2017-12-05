#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_django-sftpserver
------------

Tests for `django-sftpserver` models module.
"""
import stat as _stat

from django.test import TestCase

from django_sftpserver import models


class TestDjango_sftpserver_files(TestCase):

    def setUp(self):
        self.root = models.Root.objects.create(name="test")
        self.root.mkdir('/')
        self.sample_data = b'hello world'
        self.sample_data_2 = b'hello world, This is sample data.'

    def test_ls_none(self):
        result = self.root.ls('/')
        self.assertEqual(len(result), 0)

    def test_ls_file(self):
        self.root.put('/a', self.sample_data)
        result = self.root.ls('/')
        self.assertEqual(len(result), 1)

    def test_ls_dir(self):
        self.root.put('/a', self.sample_data)
        self.root.put('/z/b', self.sample_data)
        self.root.put('/z/c', self.sample_data)
        self.root.put('/z/z/d', self.sample_data)
        self.root.put('/z/z/e', self.sample_data)
        self.assertEqual(len(self.root.ls('/')), 2)
        self.assertEqual(len(self.root.ls('/z/')), 3)
        self.assertEqual(len(self.root.ls('/z/z/')), 2)

    def test_get(self):
        self.root.put('/a', self.sample_data)
        self.assertEqual(self.root.get('/a').data, self.sample_data)

    def test_put_file(self):
        self.root.put('/a', self.sample_data)
        self.assertEqual(models.Data.objects.all().count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.assertEqual(models.MetaFile.objects.get(root=self.root, path='/a').data, self.sample_data)

        self.root.put('/a', self.sample_data_2)
        self.assertEqual(models.MetaFile.objects.get(root=self.root, path='/a').data, self.sample_data_2)

    def test_put_file_recursive(self):
        self.root.put('/a/b/c', self.sample_data)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 1)
        self.assertEqual(models.MetaFile.objects.get(root=self.root, path='/a/b/c').data, self.sample_data)

    def test_stat(self):
        self.root.put('/a', self.sample_data)
        self.root.mkdir('/b/')
        self.assertEqual(self.root.get('/a').stat.st_mode, _stat.S_IFREG)
        self.assertEqual(self.root.get('/b/').stat.st_mode, _stat.S_IFDIR)

    def test_remove_file(self):
        self.root.put('/a', self.sample_data)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.root.remove('/a')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 0)

    def test_remove_dir(self):
        self.root.mkdir('/a/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.root.remove('/a/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 0)

    def test_remove_subdir(self):
        self.root.put('/a/b/c', self.sample_data)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 1)
        self.root.remove('/a/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 0)

    def test_rename_file(self):
        self.root.put('/a', self.sample_data)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.assertEqual(models.MetaFile.objects.get(root=self.root, path='/a').data, self.sample_data)
        self.root.rename('/a', '/b')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 0)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/b').count(), 1)
        self.assertEqual(models.MetaFile.objects.get(root=self.root, path='/b').data, self.sample_data)

    def test_rename_dir(self):
        self.root.mkdir('/a/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.root.rename('/a/', '/b/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 0)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/b').count(), 1)

    def test_rename_subdir(self):
        self.root.put('/a/b/c', self.sample_data)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 1)
        self.root.rename('/a/b/', '/a/z/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 0)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/z/c').count(), 1)

    def test_mkdir(self):
        self.root.mkdir('/a/b/c/')
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b').count(), 1)
        self.assertEqual(models.MetaFile.objects.filter(root=self.root, path='/a/b/c').count(), 1)


class TestDjango_sftpserver_commit(TestCase):

    def setUp(self):
        self.root = models.Root.objects.create(name="test")
        self.root.mkdir('/')

    def test_commit(self):
        self.root.commit()
