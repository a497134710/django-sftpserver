=====
Usage
=====

To use django-sftpserver in a project, add it to your `INSTALLED_APPS`:

.. code-block:: python

    INSTALLED_APPS = (
        ...
        'django_sftpserver.apps.DjangoSftpserverConfig',
        ...
    )

Add django-sftpserver's URL patterns:

.. code-block:: python

    from django_sftpserver import urls as django_sftpserver_urls


    urlpatterns = [
        ...
        url(r'^', include(django_sftpserver_urls)),
        ...
    ]
