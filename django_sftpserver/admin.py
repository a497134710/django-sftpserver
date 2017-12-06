# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

from django.contrib import admin
from . import models


@admin.register(models.AuthorizedKey)
class AuthorizedKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'key_type')
    # list_filter = ()


@admin.register(models.Root)
class RootAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'branch')


@admin.register(models.MetaFile)
class MetaFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'root', 'path')


@admin.register(models.Data)
class DataAdmin(admin.ModelAdmin):
    list_display = ('id', 'size', 'key', 'parent_key')


@admin.register(models.Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ('id', 'root', 'name', 'creator', 'created_at', 'key')


@admin.register(models.CommitItem)
class CommitItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'commit', 'path', 'key')


@admin.register(models.StorageAccessInfo)
class StorageAccessInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'storage_class', 'args', 'kwargs')
